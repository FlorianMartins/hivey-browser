// Hivey Cyber: right-click menus for pages, links and selected text.

import {SELECTION_TOOLS, TOOLS, target, toolUrl} from './tools.js';

const t = key => chrome.i18n.getMessage(key) || key;

function buildMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({id: 'root', title: t('extName'), contexts: ['page', 'link', 'selection']});
    for (const tool of TOOLS) {
      chrome.contextMenus.create({id: `page:${tool.id}`, parentId: 'root', title: t(`tool_${tool.id}`),
                                  contexts: ['page']});
      chrome.contextMenus.create({id: `link:${tool.id}`, parentId: 'root', title: t(`tool_${tool.id}`),
                                  contexts: ['link']});
    }
    for (const tool of SELECTION_TOOLS) {
      chrome.contextMenus.create({id: `selection:${tool.id}`, parentId: 'root', title: t(`tool_${tool.id}`),
                                  contexts: ['selection']});
    }
  });
}

chrome.runtime.onInstalled.addListener(buildMenus);
chrome.runtime.onStartup.addListener(buildMenus);

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const [kind, id] = String(info.menuItemId).split(':');
  let url = null;
  if (kind === 'selection') {
    const tool = SELECTION_TOOLS.find(s => s.id === id);
    url = tool && info.selectionText ? tool.url(info.selectionText) : null;
  } else {
    const tool = TOOLS.find(s => s.id === id);
    const page = target(kind === 'link' ? info.linkUrl : (info.pageUrl || tab?.url || ''));
    url = tool && page ? await toolUrl(tool, page) : null;
  }
  if (url) {
    chrome.tabs.create({url, index: tab ? tab.index + 1 : undefined, openerTabId: tab?.id});
  }
});
