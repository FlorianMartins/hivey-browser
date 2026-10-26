// Hivey Cyber: the security lookups Firefox users add with extensions, in one
// place. Every tool opens an external service in a new tab, only when the
// user asks; the service receives the domain, address or text analysed.

export const TOOLS = [
  // Identity of a site
  {id: 'whois', group: 'identity', needs: 'domain', url: d => `https://www.whois.com/whois/${d}`},
  {id: 'geoip', group: 'identity', needs: 'ip', url: ip => `https://ipinfo.io/${ip}`},
  {id: 'dns', group: 'identity', needs: 'domain',
   url: d => `https://dnschecker.org/all-dns-records-of-domain.php?query=${d}&rtype=ALL`},
  {id: 'certificates', group: 'identity', needs: 'domain', url: d => `https://crt.sh/?q=${d}`},
  // Reputation
  {id: 'virustotal', group: 'reputation', needs: 'url',
   url: u => `https://www.virustotal.com/gui/search/${encodeURIComponent(u)}`},
  {id: 'urlscan', group: 'reputation', needs: 'domain', url: d => `https://urlscan.io/domain/${d}`},
  {id: 'shodan', group: 'reputation', needs: 'domain',
   url: d => `https://www.shodan.io/search?query=hostname%3A${encodeURIComponent(d)}`},
  // Security of the site
  {id: 'ssllabs', group: 'security', needs: 'domain',
   url: d => `https://www.ssllabs.com/ssltest/analyze.html?d=${d}&hideResults=on`},
  {id: 'headers', group: 'security', needs: 'url',
   url: u => `https://securityheaders.com/?q=${encodeURIComponent(u)}&followRedirects=on`},
  {id: 'observatory', group: 'security', needs: 'domain',
   url: d => `https://developer.mozilla.org/en-US/observatory/analyze?host=${d}`},
  // History
  {id: 'wayback', group: 'history', needs: 'url', url: u => `https://web.archive.org/web/*/${u}`},
];

// Tools for selected text: a hash, IP or domain (VirusTotal), an email (HIBP).
export const SELECTION_TOOLS = [
  {id: 'vtSearch', url: s => `https://www.virustotal.com/gui/search/${encodeURIComponent(s.trim())}`},
  {id: 'hibp', url: s => `https://haveibeenpwned.com/account/${encodeURIComponent(s.trim())}`},
];

export function target(urlString) {
  try {
    const url = new URL(urlString);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      return null;
    }
    return {url: url.href, domain: url.hostname};
  } catch {
    return null;
  }
}

const IPV4 = /^\d{1,3}(\.\d{1,3}){3}$/;

// The first IPv4 address of a domain, through Quad9's DNS-over-HTTPS JSON
// API (only when the user asks for the geolocation).
export async function resolveIp(domain) {
  if (IPV4.test(domain)) {
    return domain;
  }
  const response = await fetch(
      `https://dns.quad9.net:5053/dns-query?name=${encodeURIComponent(domain)}&type=A`,
      {headers: {accept: 'application/dns-json'}, credentials: 'omit', cache: 'no-store'});
  const json = await response.json();
  const answer = (json.Answer || []).find(a => a.type === 1);
  return answer ? answer.data : null;
}

export async function toolUrl(tool, page) {
  if (tool.needs === 'domain') {
    return tool.url(page.domain);
  }
  if (tool.needs === 'url') {
    return tool.url(page.url);
  }
  const ip = await resolveIp(page.domain);
  return ip ? tool.url(ip) : null;
}
