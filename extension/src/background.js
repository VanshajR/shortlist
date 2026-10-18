// The toolbar button and Alt+Shift+F both ask the page to fill; elsewhere they open the details page.
const WORKDAY = /^https:\/\/[^/]+\.(myworkdayjobs|myworkdaysite|myworkday)\.com\//;

async function fill(tab) {
  if (!tab || !WORKDAY.test(tab.url || "")) return chrome.runtime.openOptionsPage();
  chrome.tabs.sendMessage(tab.id, { type: "fill" }).catch(() => {});
}

chrome.action.onClicked.addListener(fill);
chrome.commands.onCommand.addListener(async (command, tab) => {
  if (command === "fill") fill(tab || (await chrome.tabs.query({ active: true, currentWindow: true }))[0]);
});
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "options") chrome.runtime.openOptionsPage();
});
chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === "install") chrome.runtime.openOptionsPage();
});
