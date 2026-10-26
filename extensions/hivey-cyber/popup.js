// Hivey Cyber popup: the tools for the current tab, grouped.

import {TOOLS, target, toolUrl} from './tools.js';

const t = key => chrome.i18n.getMessage(key) || key;
const GROUPS = ['identity', 'reputation', 'security', 'history'];

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === 'class') {
      node.className = value;
    } else if (key === 'text') {
      node.textContent = value;
    } else if (key.startsWith('on')) {
      node.addEventListener(key.slice(2), value);
    } else {
      node.setAttribute(key, value);
    }
  }
  node.append(...children);
  return node;
}

async function main() {
  document.getElementById('title').textContent = t('extName');
  document.getElementById('note').textContent = t('popupNote');
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  const page = tab ? target(tab.url || '') : null;
  const main = document.getElementById('tools');
  if (!page) {
    document.getElementById('target').textContent = '';
    main.append(el('p', {class: 'empty', text: t('popupNoSite')}));
    return;
  }
  document.getElementById('target').textContent = page.domain;
  for (const group of GROUPS) {
    const list = el('div', {class: 'grid'});
    for (const tool of TOOLS.filter(x => x.group === group)) {
      list.append(el('button', {
        class: 'tool',
        title: t(`tool_${tool.id}_hint`),
        onclick: async () => {
          const url = await toolUrl(tool, page).catch(() => null);
          if (url) {
            chrome.tabs.create({url, index: tab.index + 1, openerTabId: tab.id});
            window.close();
          }
        },
      }, el('span', {class: 'name', text: t(`tool_${tool.id}`)}),
         el('span', {class: 'hint', text: t(`tool_${tool.id}_hint`)})));
    }
    main.append(el('section', {}, el('h2', {text: t(`group_${group}`)}), list));
  }
}

main();
