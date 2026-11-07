/**
 * Integer minor-unit money helpers for the commercial control plane.
 *
 * Amounts arrive from the API as integers in the currency's minor unit with an ISO 4217 code and
 * exponent. Formatting and parsing use string/BigInt arithmetic only: the UI never performs
 * floating-point price calculations (Master Architecture §20, Appendix C).
 */

// Mirrors backend apps/commercial/money.py CURRENCY_EXPONENTS.
export const CURRENCY_EXPONENTS: Record<string, number> = {
  AED: 2, AUD: 2, BRL: 2, CAD: 2, CHF: 2, CNY: 2, CZK: 2, DKK: 2, EUR: 2, GBP: 2, HKD: 2, INR: 2, MXN: 2,
  MYR: 2, NOK: 2, NZD: 2, PLN: 2, QAR: 2, SAR: 2, SEK: 2, SGD: 2, THB: 2, TRY: 2, USD: 2, ZAR: 2,
  CLP: 0, ISK: 0, JPY: 0, KRW: 0, VND: 0,
  BHD: 3, JOD: 3, KWD: 3, OMR: 3, TND: 3,
};

export function currencyExponent(currency: string, fallback?: number | null): number {
  const exponent = CURRENCY_EXPONENTS[(currency || "").toUpperCase()];
  if (exponent !== undefined) return exponent;
  return fallback ?? 2;
}

/** Format an integer minor-unit amount exactly, e.g. (24900, "GBP") → "£249.00". */
export function formatMinor(
  amountMinor: number | null | undefined,
  currency: string,
  exponent?: number | null,
  locale?: string
): string {
  if (amountMinor === null || amountMinor === undefined) return "—";
  const exp = exponent ?? currencyExponent(currency);
  const negative = amountMinor < 0;
  const digits = BigInt(Math.abs(Math.trunc(amountMinor)));
  const scale = BigInt(10) ** BigInt(exp);
  const major = digits / scale;
  const minor = (digits % scale).toString().padStart(exp, "0");

  try {
    const parts = new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      minimumFractionDigits: exp,
      maximumFractionDigits: exp,
    }).formatToParts(major);
    const text = parts
      .map((part) => (part.type === "fraction" ? minor : part.value))
      .join("");
    return negative ? `-${text}` : text;
  } catch {
    return `${negative ? "-" : ""}${currency} ${major.toString()}${exp ? `.${minor}` : ""}`;
  }
}

/**
 * Parse a typed major-unit amount ("249", "249.5", "1,249.00") into integer minor units without floats.
 * Returns null for empty input; throws for invalid input or too many decimal places.
 */
export function parseMajorToMinor(input: string, exponent: number): number | null {
  const cleaned = input.replace(/[\s,]/g, "");
  if (cleaned === "") return null;
  if (!/^\d+(\.\d+)?$/.test(cleaned)) {
    throw new Error(`"${input}" is not a valid non-negative amount.`);
  }
  const [whole, fraction = ""] = cleaned.split(".");
  if (fraction.length > exponent) {
    throw new Error(`Amounts in this currency allow at most ${exponent} decimal place(s).`);
  }
  const minor = BigInt(whole) * BigInt(10) ** BigInt(exponent) + BigInt((fraction + "0".repeat(exponent)).slice(0, exponent) || "0");
  if (minor > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new Error("Amount is too large.");
  }
  return Number(minor);
}

/** Basis points → percentage text without floats, e.g. 850 → "8.5%". */
export function formatBasisPoints(bps: number | null | undefined): string {
  if (bps === null || bps === undefined) return "—";
  const whole = Math.trunc(bps / 100);
  const fraction = (bps % 100).toString().padStart(2, "0").replace(/0+$/, "");
  return `${whole}${fraction ? `.${fraction}` : ""}%`;
}

/** Parse a percentage string ("8", "8.5", "12.25") into basis points without floats. */
export function parsePercentToBps(input: string): number | null {
  const cleaned = input.replace(/[\s%]/g, "");
  if (cleaned === "") return null;
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) {
    throw new Error("Percentages allow at most 2 decimal places (basis-point precision).");
  }
  const [whole, fraction = ""] = cleaned.split(".");
  const bps = Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
  if (bps > 10000) throw new Error("Percentage cannot exceed 100%.");
  return bps;
}
