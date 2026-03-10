/**
 * Centralized validators for the Consorcio Canalero application.
 * These functions provide consistent validation logic across all components.
 */
// @ts-nocheck


// ===========================================
// EMAIL VALIDATION
// ===========================================

/**
 * Maximum allowed email length per RFC 5321.
 */function stryNS_9fa48() {
  var g = typeof globalThis === 'object' && globalThis && globalThis.Math === Math && globalThis || new Function("return this")();
  var ns = g.__stryker__ || (g.__stryker__ = {});
  if (ns.activeMutant === undefined && g.process && g.process.env && g.process.env.__STRYKER_ACTIVE_MUTANT__) {
    ns.activeMutant = g.process.env.__STRYKER_ACTIVE_MUTANT__;
  }
  function retrieveNS() {
    return ns;
  }
  stryNS_9fa48 = retrieveNS;
  return retrieveNS();
}
stryNS_9fa48();
function stryCov_9fa48() {
  var ns = stryNS_9fa48();
  var cov = ns.mutantCoverage || (ns.mutantCoverage = {
    static: {},
    perTest: {}
  });
  function cover() {
    var c = cov.static;
    if (ns.currentTestId) {
      c = cov.perTest[ns.currentTestId] = cov.perTest[ns.currentTestId] || {};
    }
    var a = arguments;
    for (var i = 0; i < a.length; i++) {
      c[a[i]] = (c[a[i]] || 0) + 1;
    }
  }
  stryCov_9fa48 = cover;
  cover.apply(null, arguments);
}
function stryMutAct_9fa48(id) {
  var ns = stryNS_9fa48();
  function isActive(id) {
    if (ns.activeMutant === id) {
      if (ns.hitCount !== void 0 && ++ns.hitCount > ns.hitLimit) {
        throw new Error('Stryker: Hit count limit reached (' + ns.hitCount + ')');
      }
      return true;
    }
    return false;
  }
  stryMutAct_9fa48 = isActive;
  return isActive(id);
}
export const MAX_EMAIL_LENGTH = 254;

/**
 * Email regex that validates format without being vulnerable to ReDoS.
 * Based on HTML5 email validation specification with improvements.
 */
const EMAIL_REGEX = stryMutAct_9fa48("181") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[^a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("180") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[^a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("179") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-][a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("178") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9]))*$/ : stryMutAct_9fa48("177") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[^a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("176") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)$/ : stryMutAct_9fa48("175") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[^a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("174") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[^a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("173") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-][a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("172") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("171") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[^a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("170") ? /^[^a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("169") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("168") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*/ : stryMutAct_9fa48("167") ? /[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : (stryCov_9fa48("167", "168", "169", "170", "171", "172", "173", "174", "175", "176", "177", "178", "179", "180", "181"), /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/);

/**
 * Validates an email address.
 * @param email - The email to validate
 * @returns true if the email is valid
 */
export function isValidEmail(email: string): boolean {
  if (stryMutAct_9fa48("182")) {
    {}
  } else {
    stryCov_9fa48("182");
    if (stryMutAct_9fa48("185") ? !email && typeof email !== 'string' : stryMutAct_9fa48("184") ? false : stryMutAct_9fa48("183") ? true : (stryCov_9fa48("183", "184", "185"), (stryMutAct_9fa48("186") ? email : (stryCov_9fa48("186"), !email)) || (stryMutAct_9fa48("188") ? typeof email === 'string' : stryMutAct_9fa48("187") ? false : (stryCov_9fa48("187", "188"), typeof email !== (stryMutAct_9fa48("189") ? "" : (stryCov_9fa48("189"), 'string')))))) return stryMutAct_9fa48("190") ? true : (stryCov_9fa48("190"), false);
    if (stryMutAct_9fa48("193") ? email.length === 0 && email.length > MAX_EMAIL_LENGTH : stryMutAct_9fa48("192") ? false : stryMutAct_9fa48("191") ? true : (stryCov_9fa48("191", "192", "193"), (stryMutAct_9fa48("195") ? email.length !== 0 : stryMutAct_9fa48("194") ? false : (stryCov_9fa48("194", "195"), email.length === 0)) || (stryMutAct_9fa48("198") ? email.length <= MAX_EMAIL_LENGTH : stryMutAct_9fa48("197") ? email.length >= MAX_EMAIL_LENGTH : stryMutAct_9fa48("196") ? false : (stryCov_9fa48("196", "197", "198"), email.length > MAX_EMAIL_LENGTH)))) return stryMutAct_9fa48("199") ? true : (stryCov_9fa48("199"), false);
    return EMAIL_REGEX.test(email);
  }
}

/**
 * Validates email for Mantine form validation.
 * @param value - The email value
 * @returns Error message or null if valid
 */
export function validateEmail(value: string): string | null {
  if (stryMutAct_9fa48("200")) {
    {}
  } else {
    stryCov_9fa48("200");
    if (stryMutAct_9fa48("203") ? false : stryMutAct_9fa48("202") ? true : stryMutAct_9fa48("201") ? value : (stryCov_9fa48("201", "202", "203"), !value)) return stryMutAct_9fa48("204") ? "" : (stryCov_9fa48("204"), 'El email es requerido');
    if (stryMutAct_9fa48("208") ? value.length <= MAX_EMAIL_LENGTH : stryMutAct_9fa48("207") ? value.length >= MAX_EMAIL_LENGTH : stryMutAct_9fa48("206") ? false : stryMutAct_9fa48("205") ? true : (stryCov_9fa48("205", "206", "207", "208"), value.length > MAX_EMAIL_LENGTH)) return stryMutAct_9fa48("209") ? "" : (stryCov_9fa48("209"), 'Email demasiado largo');
    if (stryMutAct_9fa48("212") ? false : stryMutAct_9fa48("211") ? true : stryMutAct_9fa48("210") ? isValidEmail(value) : (stryCov_9fa48("210", "211", "212"), !isValidEmail(value))) return stryMutAct_9fa48("213") ? "" : (stryCov_9fa48("213"), 'Email invalido');
    return null;
  }
}

// ===========================================
// PHONE VALIDATION
// ===========================================

/**
 * Phone regex for Argentine phone numbers.
 * Accepts formats: +54..., 54..., 0..., or just digits.
 */
const PHONE_REGEX = stryMutAct_9fa48("220") ? /^(\+?54|0)?[1-9]\D{9,10}$/ : stryMutAct_9fa48("219") ? /^(\+?54|0)?[1-9]\d$/ : stryMutAct_9fa48("218") ? /^(\+?54|0)?[^1-9]\d{9,10}$/ : stryMutAct_9fa48("217") ? /^(\+54|0)?[1-9]\d{9,10}$/ : stryMutAct_9fa48("216") ? /^(\+?54|0)[1-9]\d{9,10}$/ : stryMutAct_9fa48("215") ? /^(\+?54|0)?[1-9]\d{9,10}/ : stryMutAct_9fa48("214") ? /(\+?54|0)?[1-9]\d{9,10}$/ : (stryCov_9fa48("214", "215", "216", "217", "218", "219", "220"), /^(\+?54|0)?[1-9]\d{9,10}$/);

/**
 * Validates an Argentine phone number.
 * @param phone - The phone number to validate
 * @returns true if the phone is valid
 */
export function isValidPhone(phone: string): boolean {
  if (stryMutAct_9fa48("221")) {
    {}
  } else {
    stryCov_9fa48("221");
    if (stryMutAct_9fa48("224") ? !phone && typeof phone !== 'string' : stryMutAct_9fa48("223") ? false : stryMutAct_9fa48("222") ? true : (stryCov_9fa48("222", "223", "224"), (stryMutAct_9fa48("225") ? phone : (stryCov_9fa48("225"), !phone)) || (stryMutAct_9fa48("227") ? typeof phone === 'string' : stryMutAct_9fa48("226") ? false : (stryCov_9fa48("226", "227"), typeof phone !== (stryMutAct_9fa48("228") ? "" : (stryCov_9fa48("228"), 'string')))))) return stryMutAct_9fa48("229") ? true : (stryCov_9fa48("229"), false);
    const cleanPhone = phone.replace(stryMutAct_9fa48("231") ? /[\S\-().]/g : stryMutAct_9fa48("230") ? /[^\s\-().]/g : (stryCov_9fa48("230", "231"), /[\s\-().]/g), stryMutAct_9fa48("232") ? "Stryker was here!" : (stryCov_9fa48("232"), ''));
    return PHONE_REGEX.test(cleanPhone);
  }
}

/**
 * Validates phone for Mantine form validation.
 * @param value - The phone value
 * @returns Error message or null if valid
 */
export function validatePhone(value: string): string | null {
  if (stryMutAct_9fa48("233")) {
    {}
  } else {
    stryCov_9fa48("233");
    if (stryMutAct_9fa48("236") ? false : stryMutAct_9fa48("235") ? true : stryMutAct_9fa48("234") ? value : (stryCov_9fa48("234", "235", "236"), !value)) return null; // Phone is usually optional
    if (stryMutAct_9fa48("239") ? false : stryMutAct_9fa48("238") ? true : stryMutAct_9fa48("237") ? isValidPhone(value) : (stryCov_9fa48("237", "238", "239"), !isValidPhone(value))) return stryMutAct_9fa48("240") ? "" : (stryCov_9fa48("240"), 'Telefono invalido');
    return null;
  }
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
  if (stryMutAct_9fa48("241")) {
    {}
  } else {
    stryCov_9fa48("241");
    if (stryMutAct_9fa48("244") ? !cuit && typeof cuit !== 'string' : stryMutAct_9fa48("243") ? false : stryMutAct_9fa48("242") ? true : (stryCov_9fa48("242", "243", "244"), (stryMutAct_9fa48("245") ? cuit : (stryCov_9fa48("245"), !cuit)) || (stryMutAct_9fa48("247") ? typeof cuit === 'string' : stryMutAct_9fa48("246") ? false : (stryCov_9fa48("246", "247"), typeof cuit !== (stryMutAct_9fa48("248") ? "" : (stryCov_9fa48("248"), 'string')))))) return stryMutAct_9fa48("249") ? true : (stryCov_9fa48("249"), false);
    const cleanCUIT = cuit.replace(stryMutAct_9fa48("251") ? /[^\D]/g : stryMutAct_9fa48("250") ? /[\d]/g : (stryCov_9fa48("250", "251"), /[^\d]/g), stryMutAct_9fa48("252") ? "Stryker was here!" : (stryCov_9fa48("252"), ''));
    if (stryMutAct_9fa48("255") ? cleanCUIT.length === 11 : stryMutAct_9fa48("254") ? false : stryMutAct_9fa48("253") ? true : (stryCov_9fa48("253", "254", "255"), cleanCUIT.length !== 11)) return stryMutAct_9fa48("256") ? true : (stryCov_9fa48("256"), false);
    const weights = stryMutAct_9fa48("257") ? [] : (stryCov_9fa48("257"), [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]);
    let sum = 0;
    for (let i = 0; stryMutAct_9fa48("260") ? i >= 10 : stryMutAct_9fa48("259") ? i <= 10 : stryMutAct_9fa48("258") ? false : (stryCov_9fa48("258", "259", "260"), i < 10); stryMutAct_9fa48("261") ? i-- : (stryCov_9fa48("261"), i++)) {
      if (stryMutAct_9fa48("262")) {
        {}
      } else {
        stryCov_9fa48("262");
        stryMutAct_9fa48("263") ? sum -= Number.parseInt(cleanCUIT[i], 10) * weights[i] : (stryCov_9fa48("263"), sum += stryMutAct_9fa48("264") ? Number.parseInt(cleanCUIT[i], 10) / weights[i] : (stryCov_9fa48("264"), Number.parseInt(cleanCUIT[i], 10) * weights[i]));
      }
    }
    const checkDigit = Number.parseInt(cleanCUIT[10], 10);
    const calculatedCheckDigit = stryMutAct_9fa48("265") ? 11 + sum % 11 : (stryCov_9fa48("265"), 11 - (stryMutAct_9fa48("266") ? sum * 11 : (stryCov_9fa48("266"), sum % 11)));
    const finalDigit = (stryMutAct_9fa48("269") ? calculatedCheckDigit !== 11 : stryMutAct_9fa48("268") ? false : stryMutAct_9fa48("267") ? true : (stryCov_9fa48("267", "268", "269"), calculatedCheckDigit === 11)) ? 0 : (stryMutAct_9fa48("272") ? calculatedCheckDigit !== 10 : stryMutAct_9fa48("271") ? false : stryMutAct_9fa48("270") ? true : (stryCov_9fa48("270", "271", "272"), calculatedCheckDigit === 10)) ? 9 : calculatedCheckDigit;
    return stryMutAct_9fa48("275") ? checkDigit !== finalDigit : stryMutAct_9fa48("274") ? false : stryMutAct_9fa48("273") ? true : (stryCov_9fa48("273", "274", "275"), checkDigit === finalDigit);
  }
}

/**
 * Validates CUIT for Mantine form validation.
 * @param value - The CUIT value
 * @returns Error message or null if valid
 */
export function validateCUIT(value: string): string | null {
  if (stryMutAct_9fa48("276")) {
    {}
  } else {
    stryCov_9fa48("276");
    if (stryMutAct_9fa48("279") ? false : stryMutAct_9fa48("278") ? true : stryMutAct_9fa48("277") ? value : (stryCov_9fa48("277", "278", "279"), !value)) return stryMutAct_9fa48("280") ? "" : (stryCov_9fa48("280"), 'El CUIT es requerido');
    if (stryMutAct_9fa48("283") ? false : stryMutAct_9fa48("282") ? true : stryMutAct_9fa48("281") ? isValidCUIT(value) : (stryCov_9fa48("281", "282", "283"), !isValidCUIT(value))) return stryMutAct_9fa48("284") ? "" : (stryCov_9fa48("284"), 'CUIT invalido');
    return null;
  }
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
  RESOLUCION: 2000
} as const;

/**
 * Creates a length validator for Mantine forms.
 * @param minLength - Minimum required length
 * @param maxLength - Maximum allowed length
 * @param fieldName - Name of the field for error messages
 * @returns Validation function
 */
export function createLengthValidator(minLength: number, maxLength: number, fieldName: string): (value: string) => string | null {
  if (stryMutAct_9fa48("285")) {
    {}
  } else {
    stryCov_9fa48("285");
    return (value: string) => {
      if (stryMutAct_9fa48("286")) {
        {}
      } else {
        stryCov_9fa48("286");
        if (stryMutAct_9fa48("290") ? value.length >= minLength : stryMutAct_9fa48("289") ? value.length <= minLength : stryMutAct_9fa48("288") ? false : stryMutAct_9fa48("287") ? true : (stryCov_9fa48("287", "288", "289", "290"), value.length < minLength)) {
          if (stryMutAct_9fa48("291")) {
            {}
          } else {
            stryCov_9fa48("291");
            return stryMutAct_9fa48("292") ? `` : (stryCov_9fa48("292"), `${fieldName} debe tener al menos ${minLength} caracteres`);
          }
        }
        if (stryMutAct_9fa48("296") ? value.length <= maxLength : stryMutAct_9fa48("295") ? value.length >= maxLength : stryMutAct_9fa48("294") ? false : stryMutAct_9fa48("293") ? true : (stryCov_9fa48("293", "294", "295", "296"), value.length > maxLength)) {
          if (stryMutAct_9fa48("297")) {
            {}
          } else {
            stryCov_9fa48("297");
            return stryMutAct_9fa48("298") ? `` : (stryCov_9fa48("298"), `${fieldName} no puede exceder ${maxLength} caracteres`);
          }
        }
        return null;
      }
    };
  }
}

/**
 * Pre-built validators for common fields.
 */
export const validators = stryMutAct_9fa48("299") ? {} : (stryCov_9fa48("299"), {
  titulo: createLengthValidator(5, MAX_LENGTHS.TITULO, stryMutAct_9fa48("300") ? "" : (stryCov_9fa48("300"), 'El titulo')),
  descripcion: createLengthValidator(10, MAX_LENGTHS.DESCRIPCION, stryMutAct_9fa48("301") ? "" : (stryCov_9fa48("301"), 'La descripcion')),
  nombre: createLengthValidator(2, MAX_LENGTHS.NOMBRE, stryMutAct_9fa48("302") ? "" : (stryCov_9fa48("302"), 'El nombre')),
  resolucion: createLengthValidator(5, MAX_LENGTHS.RESOLUCION, stryMutAct_9fa48("303") ? "" : (stryCov_9fa48("303"), 'La resolucion'))
});

// ===========================================
// URL VALIDATION
// ===========================================

/**
 * Validates if a string is a valid HTTP/HTTPS URL.
 * @param url - The URL to validate
 * @returns true if the URL is valid
 */
export function isValidUrl(url: string): boolean {
  if (stryMutAct_9fa48("304")) {
    {}
  } else {
    stryCov_9fa48("304");
    if (stryMutAct_9fa48("307") ? !url && typeof url !== 'string' : stryMutAct_9fa48("306") ? false : stryMutAct_9fa48("305") ? true : (stryCov_9fa48("305", "306", "307"), (stryMutAct_9fa48("308") ? url : (stryCov_9fa48("308"), !url)) || (stryMutAct_9fa48("310") ? typeof url === 'string' : stryMutAct_9fa48("309") ? false : (stryCov_9fa48("309", "310"), typeof url !== (stryMutAct_9fa48("311") ? "" : (stryCov_9fa48("311"), 'string')))))) return stryMutAct_9fa48("312") ? true : (stryCov_9fa48("312"), false);
    try {
      if (stryMutAct_9fa48("313")) {
        {}
      } else {
        stryCov_9fa48("313");
        const parsed = new URL(url);
        return stryMutAct_9fa48("316") ? parsed.protocol === 'http:' && parsed.protocol === 'https:' : stryMutAct_9fa48("315") ? false : stryMutAct_9fa48("314") ? true : (stryCov_9fa48("314", "315", "316"), (stryMutAct_9fa48("318") ? parsed.protocol !== 'http:' : stryMutAct_9fa48("317") ? false : (stryCov_9fa48("317", "318"), parsed.protocol === (stryMutAct_9fa48("319") ? "" : (stryCov_9fa48("319"), 'http:')))) || (stryMutAct_9fa48("321") ? parsed.protocol !== 'https:' : stryMutAct_9fa48("320") ? false : (stryCov_9fa48("320", "321"), parsed.protocol === (stryMutAct_9fa48("322") ? "" : (stryCov_9fa48("322"), 'https:')))));
      }
    } catch {
      if (stryMutAct_9fa48("323")) {
        {}
      } else {
        stryCov_9fa48("323");
        return stryMutAct_9fa48("324") ? true : (stryCov_9fa48("324"), false);
      }
    }
  }
}

/**
 * Validates if a string is a valid tile URL (for map layers).
 * Must be HTTPS and contain {z}, {x}, {y} placeholders.
 * @param url - The tile URL to validate
 * @returns true if the URL is a valid tile URL
 */
export function isValidTileUrl(url: string): boolean {
  if (stryMutAct_9fa48("325")) {
    {}
  } else {
    stryCov_9fa48("325");
    if (stryMutAct_9fa48("328") ? !url && typeof url !== 'string' : stryMutAct_9fa48("327") ? false : stryMutAct_9fa48("326") ? true : (stryCov_9fa48("326", "327", "328"), (stryMutAct_9fa48("329") ? url : (stryCov_9fa48("329"), !url)) || (stryMutAct_9fa48("331") ? typeof url === 'string' : stryMutAct_9fa48("330") ? false : (stryCov_9fa48("330", "331"), typeof url !== (stryMutAct_9fa48("332") ? "" : (stryCov_9fa48("332"), 'string')))))) return stryMutAct_9fa48("333") ? true : (stryCov_9fa48("333"), false);
    try {
      if (stryMutAct_9fa48("334")) {
        {}
      } else {
        stryCov_9fa48("334");
        // Allow template placeholders by temporarily replacing them
        const testUrl = url.replace(stryMutAct_9fa48("335") ? /\{[^xyz]\}/g : (stryCov_9fa48("335"), /\{[xyz]\}/g), stryMutAct_9fa48("336") ? "" : (stryCov_9fa48("336"), '0'));
        const parsed = new URL(testUrl);
        if (stryMutAct_9fa48("339") ? parsed.protocol === 'https:' : stryMutAct_9fa48("338") ? false : stryMutAct_9fa48("337") ? true : (stryCov_9fa48("337", "338", "339"), parsed.protocol !== (stryMutAct_9fa48("340") ? "" : (stryCov_9fa48("340"), 'https:')))) return stryMutAct_9fa48("341") ? true : (stryCov_9fa48("341"), false);

        // Check for required placeholders
        const hasPlaceholders = stryMutAct_9fa48("344") ? url.includes('{z}') && url.includes('{x}') || url.includes('{y}') : stryMutAct_9fa48("343") ? false : stryMutAct_9fa48("342") ? true : (stryCov_9fa48("342", "343", "344"), (stryMutAct_9fa48("346") ? url.includes('{z}') || url.includes('{x}') : stryMutAct_9fa48("345") ? true : (stryCov_9fa48("345", "346"), url.includes(stryMutAct_9fa48("347") ? "" : (stryCov_9fa48("347"), '{z}')) && url.includes(stryMutAct_9fa48("348") ? "" : (stryCov_9fa48("348"), '{x}')))) && url.includes(stryMutAct_9fa48("349") ? "" : (stryCov_9fa48("349"), '{y}')));
        return hasPlaceholders;
      }
    } catch {
      if (stryMutAct_9fa48("350")) {
        {}
      } else {
        stryCov_9fa48("350");
        return stryMutAct_9fa48("351") ? true : (stryCov_9fa48("351"), false);
      }
    }
  }
}