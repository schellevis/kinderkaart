/**
 * FNV-1a 32-bit hash — MUST match data_pipeline/hashing.py exactly.
 *
 * Python reference:
 *   _OFFSET = 2166136261
 *   _PRIME  = 16777619
 *   _MASK   = 0xFFFFFFFF
 *   for byte in s.encode("utf-8"):
 *       h ^= byte
 *       h = (h * _PRIME) & _MASK
 *   return h
 *
 * We use Math.imul for 32-bit multiply and >>> 0 to keep the result unsigned.
 */
export function fnv1a(s: string): number {
  let h = 2166136261; // FNV offset basis
  const bytes = new TextEncoder().encode(s);
  for (let i = 0; i < bytes.length; i++) {
    h ^= bytes[i];
    h = Math.imul(h, 16777619); // FNV prime
  }
  return h >>> 0; // unsigned 32-bit
}
