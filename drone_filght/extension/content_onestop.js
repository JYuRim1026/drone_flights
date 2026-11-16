// Sky Command Content Script - Runs on Official Drone One-Stop Website (https://drone.onestop.go.kr/*)

(function () {
  console.log('[Sky Command Content Script] Active on:', window.location.href);

  // ---------------------------------------------------------
  // 1. AUTO LOGIN ON LOGIN PAGE
  // ---------------------------------------------------------
  if (window.location.pathname.includes('/login')) {
    chrome.storage.local.get(['onestop_id', 'onestop_pw'], (res) => {
      const id = res.onestop_id;
      const pw = res.onestop_pw;

      if (!id || !pw) {
        console.log('[Sky Command] Login credentials not set in extension popup.');
        return;
      }

      setTimeout(() => {
        const idInput = document.querySelector('input[name="memberId"], input#memberId, input[name="id"], input[type="text"]');
        const pwInput = document.querySelector('input[name="password"], input#password, input[name="pwd"], input[type="password"]');
        const loginBtn = document.querySelector('button[type="submit"], .btn_login, #loginBtn, input[type="submit"]');

        if (idInput && pwInput) {
          idInput.value = id;
          idInput.dispatchEvent(new Event('input', { bubbles: true }));
          idInput.dispatchEvent(new Event('change', { bubbles: true }));

          pwInput.value = pw;
          pwInput.dispatchEvent(new Event('input', { bubbles: true }));
          pwInput.dispatchEvent(new Event('change', { bubbles: true }));

          console.log('[Sky Command] Auto filled ID and Password.');

          if (loginBtn) {
            setTimeout(() => {
              loginBtn.click();
            }, 500);
          }
        }
      }, 800);
    });
  }

  // ---------------------------------------------------------
  // 2. AUTO FILL ON FLIGHT APPROVAL REGISTER PAGE
  // ---------------------------------------------------------
  if (window.location.pathname.includes('/flight/register') || window.location.pathname.includes('/civilappeal')) {
    chrome.storage.local.get(['flightData'], (res) => {
      const data = res.flightData;
      if (!data || data.status !== 'ready') {
        console.log('[Sky Command] No ready flight data found in local storage.');
        return;
      }

      console.log('[Sky Command] Auto-filling flight approval registration form with:', data);

      setTimeout(() => {
        // Helper function to safely fill and trigger input/change events
        function setInputValue(selectors, value) {
          if (!value) return false;
          for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) {
              el.value = value;
              el.dispatchEvent(new Event('input', { bubbles: true }));
              el.dispatchEvent(new Event('change', { bubbles: true }));
              el.style.backgroundColor = '#ECFDF5';
              el.style.borderColor = '#10B981';
              return true;
            }
          }
          return false;
        }

        // Helper function for selects
        function setSelectValue(selectors, textMatch) {
          for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) {
              for (const opt of el.options) {
                if (opt.text.includes(textMatch) || opt.value.includes(textMatch)) {
                  opt.selected = true;
                  el.dispatchEvent(new Event('change', { bubbles: true }));
                  el.style.backgroundColor = '#ECFDF5';
                  el.style.borderColor = '#10B981';
                  return true;
                }
              }
            }
          }
          return false;
        }

        // Fill Flight Dates
        if (data.period) {
          setInputValue(['input[name*="strt"]', 'input[name*="Strt"]', '#strtDt', 'input[name*="startDate"]'], data.period.startDate);
          setInputValue(['input[name*="end"]', 'input[name*="End"]', '#endDt', 'input[name*="endDate"]'], data.period.endDate);
        }

        // Fill Purpose & Flight Method
        setSelectValue(['select[name*="purp"]', 'select[name*="Purp"]', '#flightPurp'], data.purpose || '레저');
        setSelectValue(['select[name*="meth"]', 'select[name*="Meth"]', '#flightMeth'], data.flightMethod || '시계');

        // Fill Location (Address, Coordinates, Radius, Altitude)
        if (data.area) {
          setInputValue(['input[name*="addr"]', 'input[name*="Addr"]', '#address', 'input[name="flightLoc"]'], data.area.address);
          if (data.area.latitude) {
            setInputValue(['input[name*="lat"]', 'input[name*="Lat"]', '#latitude'], String(data.area.latitude));
          }
          if (data.area.longitude) {
            setInputValue(['input[name*="lon"]', 'input[name*="Lon"]', 'input[name*="lng"]', '#longitude'], String(data.area.longitude));
          }
          if (data.area.radius) {
            setInputValue(['input[name*="rad"]', 'input[name*="Rad"]', '#radius'], String(data.area.radius));
          }
          if (data.area.altitude) {
            setInputValue(['input[name*="alt"]', 'input[name*="Alt"]', '#altitude'], String(data.area.altitude));
          }
        }

        // Fill Remarks / Notice
        if (data.etc || data.notice) {
          const combinedRemarks = `${data.etc || ''} ${data.notice || ''}`.trim();
          setInputValue(['textarea[name*="etc"]', 'textarea[name*="rmk"]', 'textarea[name*="desc"]', '#remarks'], combinedRemarks);
        }

        // Inject Floating Sky Command Success Banner
        const banner = document.createElement('div');
        banner.style.position = 'fixed';
        banner.style.top = '15px';
        banner.style.right = '15px';
        banner.style.zIndex = '999999';
        banner.style.backgroundColor = '#065F46';
        banner.style.color = '#FFFFFF';
        banner.style.padding = '14px 20px';
        banner.style.borderRadius = '10px';
        banner.style.boxShadow = '0 10px 25px rgba(0,0,0,0.3)';
        banner.style.fontSize = '0.95rem';
        banner.style.fontWeight = 'bold';
        banner.style.display = 'flex';
        banner.style.alignItems = 'center';
        banner.style.gap = '10px';
        banner.innerHTML = `
          <span style="font-size: 1.3rem;">🛸</span>
          <div>
            <div>Sky Command AI 비행승인 데이터가 자동 입력되었습니다!</div>
            <div style="font-size: 0.8rem; font-weight: normal; opacity: 0.9;">입력 내용을 최종 검토하신 후 하단의 제출 버튼을 눌러주세요.</div>
          </div>
        `;
        document.body.appendChild(banner);

      }, 1200);
    });
  }
})();
