/**
 * Centralized validators for the Consorcio Canalero application.
 * These functions provide consistent validation logic across all components.
 */

// ===========================================
// EMAIL VALIDATION
// ===========================================

/**
 * Maximum allowed email length per RFC 5321.
 */
export const MAX_EMAIL_LENGTH = 254;

/**
 * Email regex that validates format without being vulnerable to ReDoS.
 * Based on HTML5 email validation specification with improvements.
 */
const EMAIL_REGEX =
  /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/;

/**
 * Validates an email address.
 * @param email - The email to validate
 * @returns true if the email is valid
 */
export function isValidEmail(email: string): boolean {
  if (!email || typeof email !== 'string') return false;
  if (email.length === 0 || email.length > MAX_EMAIL_LENGTH) return false;
  return EMAIL_REGEX.test(email);
}

/**
 * Validates email for Mantine form validation.
 * @param value - The email value
 * @returns Error message or null if valid
 */
export function validateEmail(value: string): string | null {
  if (!value) return 'El email es requerido';
  if (value.length > MAX_EMAIL_LENGTH) return 'Email demasiado largo';
  if (!isValidEmail(value)) return 'Email invalido';
  return null;
}

// ===========================================
// PHONE VALIDATION
// ===========================================

/**
 * Phone regex for Argentine phone numbers.
 * Accepts formats: +54..., 54..., 0..., or just digits.
 */
const PHONE_REGEX = /^(\+?54|0)?[1-9]\d{9,10}$/;

/**
 * Validates an Argentine phone number.
 * @param phone - The phone number to validate
 * @returns true if the phone is valid
 */
export function isValidPhone(phone: string): boolean {
  if (!phone || typeof phone !== 'string') return false;
  const cleanPhone = phone.replace(/[\s\-().]/g, '');
  return PHONE_REGEX.test(cleanPhone);
}

/**
 * Validates phone for Mantine form validation.
 * @param value - The phone value
 * @returns Error message or null if valid
 */
export function validatePhone(value: string): string | null {
  if (!value) return null; // Phone is usually optional
  if (!isValidPhone(value)) return 'Telefono invalido';
  return null;
}

// ===========================================
// CUIT/CUIL VALIDATION
// ===========================================

/**
 * Validates an Argentine CUIT/CUIL using the modulo 11 algorithm.
 * @param cuit - The CUIT/CUIL to validate (can include dashes)
 * @returns true if the CUIT is valid
 */
export function isValidCUIT(cuit: string): boolean {
  if (!cuit || typeof cuit !== 'string') return false;

  const cleanCUIT = cuit.replace(/[^\d]/g, '');
  if (cleanCUIT.length !== 11) return false;

  const weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];
  let sum = 0;

  for (let i = 0; i < 10; i++) {
    sum += Number.parseInt(cleanCUIT[i], 10) * weights[i];
  }

  const checkDigit = Number.parseInt(cleanCUIT[10], 10);
  const calculatedCheckDigit = 11 - (sum % 11);
  const finalDigit =
    calculatedCheckDigit === 11 ? 0 : calculatedCheckDigit === 10 ? 9 : calculatedCheckDigit;

  return checkDigit === finalDigit;
}

/**
 * Validates CUIT for Mantine form validation.
 * @param value - The CUIT value
 * @returns Error message or null if valid
 */
export function validateCUIT(value: string): string | null {
  if (!value) return 'El CUIT es requerido';
  if (!isValidCUIT(value)) return 'CUIT invalido';
  return null;
}

// ===========================================
// TEXT LENGTH VALIDATION
// ===========================================

/**
 * Default maximum lengths for common fields.
 */
export const MAX_LENGTHS = {
  TITULO: 200,
  DESCRIPCION: 5000,
  NOMBRE: 100,
  TELEFONO: 20,
  RESOLUCION: 2000,
} as const;

/**
 * Creates a length validator for Mantine forms.
 * @param minLength - Minimum required length
 * @param maxLength - Maximum allowed length
 * @param fieldName - Name of the field for error messages
 * @returns Validation function
 */
export function createLengthValidator(
  minLength: number,
  maxLength: number,
  fieldName: string
): (value: string) => string | null {
  return (value: string) => {
    if (value.length < minLength) {
      return `${fieldName} debe tener al menos ${minLength} caracteres`;
    }
    if (value.length > maxLength) {
      return `${fieldName} no puede exceder ${maxLength} caracteres`;
    }
    return null;
  };
}

/**
 * Pre-built validators for common fields.
 */
export const validators = {
  titulo: createLengthValidator(5, MAX_LENGTHS.TITULO, 'El titulo'),
  descripcion: createLengthValidator(10, MAX_LENGTHS.DESCRIPCION, 'La descripcion'),
  nombre: createLengthValidator(2, MAX_LENGTHS.NOMBRE, 'El nombre'),
  resolucion: createLengthValidator(5, MAX_LENGTHS.RESOLUCION, 'La resolucion'),
};

// ===========================================
// URL VALIDATION
// ===========================================

/**
 * Validates if a string is a valid HTTP/HTTPS URL.
 * @param url - The URL to validate
 * @returns true if the URL is valid
 */
export function isValidUrl(url: string): boolean {
  if (!url || typeof url !== 'string') return false;

  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

/**
 * Validates if a string is a valid tile URL (for map layers).
 * Must be HTTPS and contain {z}, {x}, {y} placeholders.
 * @param url - The tile URL to validate
 * @returns true if the URL is a valid tile URL
 */
export function isValidTileUrl(url: string): boolean {
  if (!url || typeof url !== 'string') return false;

  try {
    // Allow template placeholders by temporarily replacing them
    const testUrl = url.replace(/\{[xyz]\}/g, '0');
    const parsed = new URL(testUrl);

    if (parsed.protocol !== 'https:') return false;

    // Check for required placeholders
    const hasPlaceholders = url.includes('{z}') && url.includes('{x}') && url.includes('{y}');
    return hasPlaceholders;
  } catch {
    return false;
  }
}
