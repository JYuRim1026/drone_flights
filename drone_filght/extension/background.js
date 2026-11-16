// Sky Command Chrome Extension Background Service Worker

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'SAVE_FLIGHT_DATA') {
    const flightData = message.payload;
    chrome.storage.local.set({ flightData: flightData, lastUpdated: Date.now() }, () => {
      console.log('[Sky Command Extension] Flight approval data stored locally:', flightData);
      sendResponse({ status: 'success', message: 'Flight data saved locally' });
    });
    return true; // Keep message channel open for async response
  }

  if (message.action === 'OPEN_ONESTOP_AND_FILL') {
    // Open Drone One-Stop flight approval page
    chrome.tabs.create({ url: 'https://drone.onestop.go.kr/civilappeal/flight/register' }, (tab) => {
      console.log('[Sky Command Extension] Opened Drone One-Stop registration tab:', tab.id);
      sendResponse({ status: 'opened', tabId: tab.id });
    });
    return true;
  }
});
