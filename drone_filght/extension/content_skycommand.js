// Sky Command Content Script - Listens for events from Streamlit Web App (http://localhost:8501)

window.addEventListener('message', (event) => {
  // Check if message is from Sky Command
  if (event.data && event.data.type === 'SKY_COMMAND_FLIGHT_APPROVAL') {
    const flightPayload = event.data.payload;
    console.log('[Sky Command Extension] Received flight approval data from Web UI:', flightPayload);

    chrome.runtime.sendMessage({
      action: 'SAVE_FLIGHT_DATA',
      payload: flightPayload
    }, (response) => {
      console.log('[Sky Command Extension] Response from background worker:', response);
    });
  }
});
