// Popup Script for Sky Command Extension

document.addEventListener('DOMContentLoaded', () => {
  const idInput = document.getElementById('onestop_id');
  const pwInput = document.getElementById('onestop_pw');
  const saveBtn = document.getElementById('save_creds_btn');
  const statusBadge = document.getElementById('data_status_badge');
  const summaryDiv = document.getElementById('data_summary');
  const openBtn = document.getElementById('open_onestop_btn');

  // Load saved credentials & flight data
  chrome.storage.local.get(['onestop_id', 'onestop_pw', 'flightData'], (result) => {
    if (result.onestop_id) idInput.value = result.onestop_id;
    if (result.onestop_pw) pwInput.value = result.onestop_pw;

    if (result.flightData) {
      const data = result.flightData;
      statusBadge.className = 'status-badge badge-ready';
      statusBadge.innerText = '✅ 준비 완료';
      
      summaryDiv.style.display = 'block';
      summaryDiv.innerHTML = `
        <b>장소</b>: ${data.area?.address || '미지정'}<br>
        <b>기간</b>: ${data.period?.startDate || ''} ~ ${data.period?.endDate || ''}<br>
        <b>고도</b>: ${data.area?.altitude || 150}m / <b>목적</b>: ${data.purpose || '레저'}
      `;
    }
  });

  // Save Credentials
  saveBtn.addEventListener('click', () => {
    const idVal = idInput.value.trim();
    const pwVal = pwInput.value.trim();
    chrome.storage.local.set({ onestop_id: idVal, onestop_pw: pwVal }, () => {
      saveBtn.innerText = '✅ 저장 완료!';
      setTimeout(() => { saveBtn.innerText = '💾 계정 정보 로컬 저장'; }, 2000);
    });
  });

  // Open Drone One-Stop & Fill Form
  openBtn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'OPEN_ONESTOP_AND_FILL' });
  });
});
