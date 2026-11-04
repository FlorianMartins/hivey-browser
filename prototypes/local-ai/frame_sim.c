// A stand-in for a game's CPU side, where no real game can run (servers, CI):
// a fixed amount of work per frame on several threads, with a frame deadline.
// The work chases pointers through a large buffer and computes, so it feels
// both CPU time and memory contention, the two things an AI engine can steal.
//
//   frame_sim --calibrate [--threads N] [--work-ms M] [--mem-mb S]
//       prints the iterations per frame that take M ms on this idle machine.
//   frame_sim --iters I [--hz H] [--threads N] [--mem-mb S] [--seconds T]
//       runs the frames, prints the result as one line of JSON.
//
// Build: cc -O2 -pthread frame_sim.c -o frame_sim -lm   (Windows: add -lwinmm)
#include <math.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif

static double now_ms(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts.tv_sec * 1e3 + ts.tv_nsec / 1e6;
}

static void sleep_ms(double ms) {
  if (ms <= 0) return;
#ifdef _WIN32
  Sleep((DWORD)ms);
#else
  struct timespec ts = {(time_t)(ms / 1e3), (long)(fmod(ms, 1e3) * 1e6)};
  nanosleep(&ts, NULL);
#endif
}

static uint32_t* g_chain;
static size_t g_chain_len;
static long g_iters;
static volatile int g_stop;
static volatile uint64_t g_sink;  // keeps the calibration from being optimized away
static pthread_barrier_t g_start, g_done;

// One unit of work: a cache-missing walk, then some arithmetic.
static uint64_t work(long iters, uint32_t* pos) {
  uint64_t acc = 0;
  uint32_t p = *pos;
  for (long i = 0; i < iters; ++i) {
    p = g_chain[p];
    acc += p;
    for (int k = 0; k < 16; ++k) acc = acc * 0x9E3779B97F4A7C15ull + k;
  }
  *pos = p;
  return acc;
}

static void* worker(void* arg) {
  uint32_t pos = (uint32_t)(uintptr_t)arg;
  uint64_t sink = 0;
  for (;;) {
    pthread_barrier_wait(&g_start);
    if (g_stop) break;
    sink += work(g_iters, &pos);
    pthread_barrier_wait(&g_done);
  }
  return (void*)(uintptr_t)sink;
}

// A single random cycle (Sattolo), so that the walk visits the whole buffer.
static void build_chain(size_t mb) {
  g_chain_len = mb * 1024 * 1024 / sizeof(uint32_t);
  g_chain = malloc(g_chain_len * sizeof(uint32_t));
  for (size_t i = 0; i < g_chain_len; ++i) g_chain[i] = (uint32_t)i;
  uint64_t r = 88172645463325252ull;
  for (size_t i = g_chain_len - 1; i > 0; --i) {
    r ^= r << 13, r ^= r >> 7, r ^= r << 17;
    size_t j = r % i;
    uint32_t t = g_chain[i];
    g_chain[i] = g_chain[j];
    g_chain[j] = t;
  }
}

static int cmp(const void* a, const void* b) {
  double d = *(const double*)a - *(const double*)b;
  return d < 0 ? -1 : d > 0;
}

static double pct(const double* sorted, size_t n, double p) {
  return sorted[(size_t)fmin(n - 1, floor(p / 100.0 * n))];
}

int main(int argc, char** argv) {
  double hz = 144, seconds = 30, work_ms = 4;
  int threads = 4, calibrate = 0;
  size_t mem_mb = 1024;
  for (int i = 1; i < argc; ++i) {
    const char* a = argv[i];
    if (!strcmp(a, "--calibrate")) calibrate = 1;
    else if (i + 1 >= argc) { fprintf(stderr, "missing value: %s\n", a); return 2; }
    else if (!strcmp(a, "--hz")) hz = atof(argv[++i]);
    else if (!strcmp(a, "--seconds")) seconds = atof(argv[++i]);
    else if (!strcmp(a, "--work-ms")) work_ms = atof(argv[++i]);
    else if (!strcmp(a, "--threads")) threads = atoi(argv[++i]);
    else if (!strcmp(a, "--mem-mb")) mem_mb = (size_t)atol(argv[++i]);
    else if (!strcmp(a, "--iters")) g_iters = atol(argv[++i]);
    else { fprintf(stderr, "unknown: %s\n", a); return 2; }
  }
  build_chain(mem_mb);

  if (calibrate) {
    uint32_t pos = 0;
    g_sink += work(2000000, &pos);  // warm the caches and the TLB
    double t = now_ms();
    g_sink += work(2000000, &pos);
    double per_iter = (now_ms() - t) / 2000000;
    printf("%ld\n", (long)(work_ms / per_iter));
    return 0;
  }
  if (g_iters <= 0) { fprintf(stderr, "--iters or --calibrate\n"); return 2; }

#ifdef _WIN32
  timeBeginPeriod(1);
#endif
  pthread_barrier_init(&g_start, NULL, (unsigned)threads + 1);
  pthread_barrier_init(&g_done, NULL, (unsigned)threads + 1);
  pthread_t* tids = malloc(sizeof(pthread_t) * (size_t)threads);
  for (int i = 0; i < threads; ++i)
    pthread_create(&tids[i], NULL, worker, (void*)(uintptr_t)(g_chain_len / (size_t)threads * (size_t)i));

  const double period = 1000.0 / hz;
  size_t cap = (size_t)(hz * seconds) + 16, n = 0;
  double* busy = malloc(sizeof(double) * cap);   // the frame's work
  double* gap = malloc(sizeof(double) * cap);    // frame start to frame start
  double begin = now_ms(), next = begin, last = 0;
  while (now_ms() - begin < seconds * 1000 && n < cap) {
    double wait = next - now_ms();
    if (wait > 2) sleep_ms(wait - 2);
    while (now_ms() < next) {}  // the precise part, as games do
    double t0 = now_ms();
    pthread_barrier_wait(&g_start);
    pthread_barrier_wait(&g_done);
    double t1 = now_ms();
    if (last > 0) gap[n] = t0 - last;
    else gap[n] = period;
    busy[n++] = t1 - t0;
    last = t0;
    next += period;
    if (next < t1) next = t1;  // late: no catching up, as a real frame
  }
  g_stop = 1;
  pthread_barrier_wait(&g_start);
  for (int i = 0; i < threads; ++i) pthread_join(tids[i], NULL);

  size_t missed = 0;
  double total_gap = 0;
  for (size_t i = 0; i < n; ++i) {
    if (busy[i] > period) ++missed;
    total_gap += gap[i];
  }
  qsort(busy, n, sizeof(double), cmp);
  qsort(gap, n, sizeof(double), cmp);
  // The 1% low: the average frame rate over the slowest 1% of frames.
  double slow = 0;
  size_t tail = n / 100 ? n / 100 : 1;
  for (size_t i = n - tail; i < n; ++i) slow += gap[i];
  printf("{\"frames\":%zu,\"fps\":%.2f,\"one_pct_low_fps\":%.2f,\"missed_pct\":%.3f,"
         "\"busy_p50\":%.3f,\"busy_p99\":%.3f,\"busy_p999\":%.3f,\"busy_max\":%.3f,\"gap_p99\":%.3f}\n",
         n, 1000.0 * (double)n / total_gap, 1000.0 / (slow / (double)tail), 100.0 * (double)missed / (double)n,
         pct(busy, n, 50), pct(busy, n, 99), pct(busy, n, 99.9), busy[n - 1], pct(gap, n, 99));
  return 0;
}
