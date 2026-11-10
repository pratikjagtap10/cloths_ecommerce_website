// Idempotency keys for checkout.
//
// One key = one checkout attempt. We reuse the SAME key while the cart and address
// stay the same, so a retry (slow network, double submit, page refresh, second tab)
// returns the original order instead of creating a new one. If the cart or address
// changes, it's a new checkout and gets a new key. The key is cleared after a
// successful payment.
//
// Stored in localStorage (not sessionStorage) so it's shared across browser tabs.

const storageKey = (userId: number | string) => `checkout_idempotency_${userId}`;

function newKey(): string {
  // crypto.randomUUID only exists in secure contexts (https or localhost)
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b: number) => b.toString(16).padStart(2, "0")).join("");
}

/** Returns the key for this exact checkout (same cart + address => same key). */
export function getCheckoutKey(userId: number | string, fingerprint: string): string {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey(userId)) ?? "null") as
      | { key: string; fingerprint: string }
      | null;
    if (saved && saved.fingerprint === fingerprint) return saved.key;
  } catch {
    /* corrupted value: fall through and create a new key */
  }
  const key = newKey();
  localStorage.setItem(storageKey(userId), JSON.stringify({ key, fingerprint }));
  return key;
}

/** Forget the key once the checkout is finished (payment succeeded). */
export function clearCheckoutKey(userId: number | string) {
  localStorage.removeItem(storageKey(userId));
}
