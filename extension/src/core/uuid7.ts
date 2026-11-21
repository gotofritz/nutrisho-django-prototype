/**
 * A version 7 UUID (RFC 9562): 48 bits of Unix time in milliseconds, then
 * random bits. The server takes only this version as a recipe's id, so that
 * ordering by id stays ordering by age (#156), and the draft makes one when
 * it starts (plan 012, D8). The time and the randomness are passed in, so
 * this stays pure and its tests are exact.
 */
export function uuidV7(milliseconds: number, random: Uint8Array): string {
  if (random.length < 10) {
    throw new RangeError("a version 7 UUID needs 10 random bytes");
  }

  const bytes = new Uint8Array(16);
  let time = milliseconds;
  for (let index = 5; index >= 0; index -= 1) {
    bytes[index] = time % 256;
    time = Math.floor(time / 256);
  }
  bytes[6] = 0x70 | (random[0]! & 0x0f);
  bytes[7] = random[1]!;
  bytes[8] = 0x80 | (random[2]! & 0x3f);
  bytes.set(random.subarray(3, 10), 9);

  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
  return [
    hex.slice(0, 4),
    hex.slice(4, 6),
    hex.slice(6, 8),
    hex.slice(8, 10),
    hex.slice(10, 16),
  ]
    .map((part) => part.join(""))
    .join("-");
}
