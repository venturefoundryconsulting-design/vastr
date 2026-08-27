/**
 * Stock quantities are decimal (backend: NUMERIC(14,4)) so the boutique can hold
 * 4.5 m of fabric or 0.125 kg of beads, not just whole garments.
 *
 * The API still sends and accepts plain JSON numbers - the backend keeps Decimal
 * internally for exact arithmetic but serializes to a number (see
 * backend/app/schemas/fields.py), so these stay `number` on this side and no
 * response type changed. What did change is input: controls must no longer force
 * whole numbers.
 */

/** Largest number of decimal places the backend will store. */
export const QTY_PRECISION = 4;

/** Smallest quantity that is still meaningfully "some stock". */
export const QTY_MIN = 0.0001;

/**
 * Shared antd <InputNumber> props for any stock quantity field.
 *
 * `step: 1` keeps the arrows behaving as they always did for whole units, while
 * still allowing a decimal to be typed directly. Deliberately no `precision`:
 * setting it would force-pad every value to 4 dp in the box ("2.0000"), which
 * reads badly for the whole-unit case that is still the common one.
 */
export const qtyInputProps = {
  min: QTY_MIN,
  step: 1,
} as const;

/** Same, but allowing negatives - for stock adjustments that reduce quantity. */
export const qtyDeltaInputProps = {
  step: 1,
} as const;

/**
 * Renders a quantity for display: 4 -> "4", 4.5 -> "4.5", 0.125 -> "0.125".
 *
 * JSON numbers already print this way, so this exists mainly to round off float
 * artifacts that can appear after arithmetic in the browser (0.1 + 0.2 and
 * friends) before the value reaches the user.
 */
export function formatQty(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "0";
  return String(Number(value.toFixed(QTY_PRECISION)));
}

/** Clamps typed input to the precision the backend can actually store. */
export function roundQty(value: number): number {
  return Number(value.toFixed(QTY_PRECISION));
}
