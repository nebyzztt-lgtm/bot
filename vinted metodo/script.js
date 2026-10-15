/**
 * MÉTODO 600€/DÍA - Lógica de presentación y Pasarela de Pago Litecoin (LTC)
 * Sin emojis, iconos vectoriales limpios SVG
 */

document.addEventListener('DOMContentLoaded', () => {
  initLtcCheckoutModal();
  initCopyActions();
  initReservationTimer();
});

/* ==========================================================================
   PASARELA DE PAGO LITECOIN (MODAL)
   ========================================================================== */
function initLtcCheckoutModal() {
  const openBtn = document.getElementById('openBuyBtn');
  const modal = document.getElementById('ltcModal');
  const closeBtn = document.getElementById('closeModalBtn');
  const confirmBtn = document.getElementById('confirmPaymentBtn');
  const emailInput = document.getElementById('buyerEmail');
  const emailError = document.getElementById('emailError');

  const mainView = document.getElementById('modalMainView');
  const processingView = document.getElementById('modalProcessingView');
  const successView = document.getElementById('modalSuccessView');
  const confirmedEmailBox = document.getElementById('confirmedEmailBox');
  const backToSiteBtn = document.getElementById('backToSiteBtn');

  // Abrir Modal
  if (openBtn && modal) {
    openBtn.addEventListener('click', () => {
      resetModalViews();
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
      document.body.style.overflow = 'hidden';
      if (emailInput) emailInput.focus();
    });
  }

  // Cerrar Modal
  function closeModal() {
    if (!modal) return;
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  if (closeBtn) closeBtn.addEventListener('click', closeModal);
  if (backToSiteBtn) backToSiteBtn.addEventListener('click', closeModal);

  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });
  }

  // Cerrar con Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.classList.contains('open')) {
      closeModal();
    }
  });

  // Resetear estados al abrir
  function resetModalViews() {
    mainView.classList.remove('hidden');
    processingView.classList.add('hidden');
    successView.classList.add('hidden');
    if (emailError) emailError.classList.remove('visible');
  }

  // Confirmar Envío de Pago y Simulación Blockchain
  if (confirmBtn) {
    confirmBtn.addEventListener('click', () => {
      const email = emailInput ? emailInput.value.trim() : '';

      // Validación simple de email
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!email || !emailRegex.test(email)) {
        if (emailError) emailError.classList.add('visible');
        if (emailInput) {
          emailInput.focus();
          emailInput.style.borderColor = '#dc2626';
        }
        return;
      }

      if (emailError) emailError.classList.remove('visible');
      if (emailInput) emailInput.style.borderColor = '';

      // Iniciar simulación de escaneo de Blockchain
      mainView.classList.add('hidden');
      processingView.classList.remove('hidden');

      const statusDesc = document.getElementById('statusDesc');
      const step2 = document.getElementById('step2');
      const step3 = document.getElementById('step3');

      // Fase 1: Rastreo
      setTimeout(() => {
        if (statusDesc) statusDesc.textContent = 'Transacción detectada en la mempool de Litecoin. Esperando confirmación...';
        if (step2) {
          step2.className = 'step-line done';
          step2.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg><span>Transacción TXID detectada en la red</span>';
        }
        if (step3) {
          step3.className = 'step-line active';
          step3.innerHTML = '<div class="mini-spin"></div><span>Confirmando bloque (1/1)...</span>';
        }
      }, 2000);

      // Fase 2: Confirmación y Entrega
      setTimeout(() => {
        processingView.classList.add('hidden');
        successView.classList.remove('hidden');
        if (confirmedEmailBox) confirmedEmailBox.textContent = email;
      }, 4200);
    });
  }
}

/* ==========================================================================
   COPIAR AL PORTAPAPELES (CON ICONOS SVG)
   ========================================================================== */
function initCopyActions() {
  const copyAmountBtn = document.getElementById('copyAmountBtn');
  const amountToCopy = document.getElementById('amountToCopy');

  const copyAddressBtn = document.getElementById('copyAddressBtn');
  const ltcAddress = document.getElementById('ltcAddress');

  function handleCopy(text, btn, successLabel) {
    navigator.clipboard.writeText(text).then(() => {
      showToast(`${successLabel} copiado`);
      const originalHTML = btn.innerHTML;
      btn.classList.add('copied');
      btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg><span>¡Copiado!</span>';
      
      setTimeout(() => {
        btn.classList.remove('copied');
        btn.innerHTML = originalHTML;
      }, 2000);
    }).catch(() => {
      showToast('Error al copiar. Selecciona manualmente.');
    });
  }

  if (copyAmountBtn && amountToCopy) {
    copyAmountBtn.addEventListener('click', () => {
      handleCopy(amountToCopy.textContent.trim(), copyAmountBtn, 'Monto LTC');
    });
  }

  if (copyAddressBtn && ltcAddress) {
    copyAddressBtn.addEventListener('click', () => {
      handleCopy(ltcAddress.textContent.trim(), copyAddressBtn, 'Dirección LTC');
    });
  }
}

/* ==========================================================================
   TOAST NOTIFICATION
   ========================================================================== */
let toastTimeout;
function showToast(message) {
  const toast = document.getElementById('toastNotification');
  const toastMsg = document.getElementById('toastMsg');
  if (!toast) return;

  if (toastMsg) toastMsg.textContent = message;
  toast.classList.remove('hidden');

  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    toast.classList.add('hidden');
  }, 2500);
}

/* ==========================================================================
   TEMPORIZADOR DE COTIZACIÓN (15 MINUTOS)
   ========================================================================== */
function initReservationTimer() {
  const timerEl = document.getElementById('modalTimer');
  if (!timerEl) return;

  let totalSeconds = 15 * 60; // 15 minutos

  function update() {
    if (totalSeconds <= 0) {
      totalSeconds = 15 * 60; // Reset
    }
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;

    const pad = (n) => String(n).padStart(2, '0');
    timerEl.textContent = `${pad(mins)}:${pad(secs)}`;
    totalSeconds--;
  }

  update();
  setInterval(update, 1000);
}
