/**
 * Captura `beforeinstallprompt` y lo guarda para un solo `prompt()`.
 *
 * No registra el service worker: eso sigue en `UpdateBanner` /
 * `vite-plugin-pwa`. Este módulo solo evita que el navegador muestre su
 * propio infobar y deja el evento a un aviso descartable.
 */

const DISMISS_KEY = 'cc-pwa-install-dismissed';

export interface BeforeInstallPromptEvent extends Event {
  readonly prompt: () => Promise<void>;
  readonly userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

type Listener = () => void;

let deferred: BeforeInstallPromptEvent | null = null;
let prompted = false;
let listening = false;
let dismissed = false;
const listeners = new Set<Listener>();

function emit(): void {
  for (const listener of listeners) listener();
}

export function subscribePwaInstall(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getPwaInstallEvent(): BeforeInstallPromptEvent | null {
  return deferred;
}

/** Cambia cuando aparece el evento, se descarta el aviso o se llama prompt(). */
export function getPwaInstallSnapshot(): string {
  const available = deferred !== null && !prompted ? '1' : '0';
  return `${available}:${isPwaInstallDismissed() ? '1' : '0'}`;
}

export function isStandaloneDisplay(): boolean {
  if (typeof window === 'undefined') return false;
  const nav = window.navigator as Navigator & { standalone?: boolean };
  if (nav.standalone === true) return true;
  return window.matchMedia('(display-mode: standalone)').matches;
}

export function isPwaInstallDismissed(): boolean {
  if (dismissed) return true;
  try {
    return localStorage.getItem(DISMISS_KEY) === '1';
  } catch {
    return false;
  }
}

export function dismissPwaInstall(): void {
  dismissed = true;
  try {
    localStorage.setItem(DISMISS_KEY, '1');
  } catch {
    // Modo privado: el aviso igual se oculta en esta visita vía el estado.
  }
  emit();
}

export function captureInstallPrompt(event: BeforeInstallPromptEvent): void {
  if (prompted || isStandaloneDisplay()) return;
  event.preventDefault();
  deferred = event;
  emit();
}

/** Llama `prompt()` como mucho una vez. El evento del navegador no se reutiliza. */
export async function runPwaInstallPrompt(): Promise<void> {
  const event = deferred;
  if (!event || prompted) return;
  prompted = true;
  deferred = null;
  emit();
  await event.prompt();
  try {
    await event.userChoice;
  } catch {
    // El diálogo nativo puede rechazar; el evento igual ya se consumió.
  }
}

export function installPwaPromptListener(): void {
  if (listening || typeof window === 'undefined') return;
  listening = true;
  window.addEventListener('beforeinstallprompt', (event) => {
    captureInstallPrompt(event as BeforeInstallPromptEvent);
  });
  window.addEventListener('appinstalled', () => {
    deferred = null;
    prompted = true;
    dismissPwaInstall();
  });
}

/** Solo tests: vuelve el módulo al estado de un documento nuevo. */
export function resetPwaInstallForTests(): void {
  deferred = null;
  prompted = false;
  listening = false;
  dismissed = false;
}
