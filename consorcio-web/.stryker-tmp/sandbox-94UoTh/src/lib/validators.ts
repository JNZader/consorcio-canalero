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
const EMAIL_REGEX = stryMutAct_9fa48("798") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[^a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("797") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[^a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("796") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-][a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("795") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9]))*$/ : stryMutAct_9fa48("794") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[^a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("793") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)$/ : stryMutAct_9fa48("792") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[^a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("791") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[^a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("790") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-][a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("789") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("788") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[^a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("787") ? /^[^a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("786") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : stryMutAct_9fa48("785") ? /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*/ : stryMutAct_9fa48("784") ? /[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/ : (stryCov_9fa48("784", "785", "786", "787", "788", "789", "790", "791", "792", "793", "794", "795", "796", "797", "798"), /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/);

/**
 * Validates an email address.
 * @param email - The email to validate
 * @returns true if the email is valid
 */
export function isValidEmail(email: string): boolean {
  if (stryMutAct_9fa48("799")) {
    {}
  } else {
    stryCov_9fa48("799");
    if (stryMutAct_9fa48("802") ? !email && typeof email !== 'string' : stryMutAct_9fa48("801") ? false : stryMutAct_9fa48("800") ? true : (stryCov_9fa48("800", "801", "802"), (stryMutAct_9fa48("803") ? email : (stryCov_9fa48("803"), !email)) || (stryMutAct_9fa48("805") ? typeof email === 'string' : stryMutAct_9fa48("804") ? false : (stryCov_9fa48("804", "805"), typeof email !== (stryMutAct_9fa48("806") ? "" : (stryCov_9fa48("806"), 'string')))))) return stryMutAct_9fa48("807") ? true : (stryCov_9fa48("807"), false);
    if (stryMutAct_9fa48("810") ? email.length === 0 && email.length > MAX_EMAIL_LENGTH : stryMutAct_9fa48("809") ? false : stryMutAct_9fa48("808") ? true : (stryCov_9fa48("808", "809", "810"), (stryMutAct_9fa48("812") ? email.length !== 0 : stryMutAct_9fa48("811") ? false : (stryCov_9fa48("811", "812"), email.length === 0)) || (stryMutAct_9fa48("815") ? email.length <= MAX_EMAIL_LENGTH : stryMutAct_9fa48("814") ? email.length >= MAX_EMAIL_LENGTH : stryMutAct_9fa48("813") ? false : (stryCov_9fa48("813", "814", "815"), email.length > MAX_EMAIL_LENGTH)))) return stryMutAct_9fa48("816") ? true : (stryCov_9fa48("816"), false);
    return EMAIL_REGEX.test(email);
  }
}

/**
 * Validates email for Mantine form validation.
 * @param value - The email value
 * @returns Error message or null if valid
 */
export function validateEmail(value: string): string | null {
  if (stryMutAct_9fa48("817")) {
    {}
  } else {
    stryCov_9fa48("817");
    if (stryMutAct_9fa48("820") ? false : stryMutAct_9fa48("819") ? true : stryMutAct_9fa48("818") ? value : (stryCov_9fa48("818", "819", "820"), !value)) return stryMutAct_9fa48("821") ? "" : (stryCov_9fa48("821"), 'El email es requerido');
    if (stryMutAct_9fa48("825") ? value.length <= MAX_EMAIL_LENGTH : stryMutAct_9fa48("824") ? value.length >= MAX_EMAIL_LENGTH : stryMutAct_9fa48("823") ? false : stryMutAct_9fa48("822") ? true : (stryCov_9fa48("822", "823", "824", "825"), value.length > MAX_EMAIL_LENGTH)) return stryMutAct_9fa48("826") ? "" : (stryCov_9fa48("826"), 'Email demasiado largo');
    if (stryMutAct_9fa48("829") ? false : stryMutAct_9fa48("828") ? true : stryMutAct_9fa48("827") ? isValidEmail(value) : (stryCov_9fa48("827", "828", "829"), !isValidEmail(value))) return stryMutAct_9fa48("830") ? "" : (stryCov_9fa48("830"), 'Email invalido');
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
const PHONE_REGEX = stryMutAct_9fa48("837") ? /^(\+?54|0)?[1-9]\D{9,10}$/ : stryMutAct_9fa48("836") ? /^(\+?54|0)?[1-9]\d$/ : stryMutAct_9fa48("835") ? /^(\+?54|0)?[^1-9]\d{9,10}$/ : stryMutAct_9fa48("834") ? /^(\+54|0)?[1-9]\d{9,10}$/ : stryMutAct_9fa48("833") ? /^(\+?54|0)[1-9]\d{9,10}$/ : stryMutAct_9fa48("832") ? /^(\+?54|0)?[1-9]\d{9,10}/ : stryMutAct_9fa48("831") ? /(\+?54|0)?[1-9]\d{9,10}$/ : (stryCov_9fa48("831", "832", "833", "834", "835", "836", "837"), /^(\+?54|0)?[1-9]\d{9,10}$/);

/**
 * Validates an Argentine phone number.
 * @param phone - The phone number to validate
 * @returns true if the phone is valid
 */
export function isValidPhone(phone: string): boolean {
  if (stryMutAct_9fa48("838")) {
    {}
  } else {
    stryCov_9fa48("838");
    if (stryMutAct_9fa48("841") ? !phone && typeof phone !== 'string' : stryMutAct_9fa48("840") ? false : stryMutAct_9fa48("839") ? true : (stryCov_9fa48("839", "840", "841"), (stryMutAct_9fa48("842") ? phone : (stryCov_9fa48("842"), !phone)) || (stryMutAct_9fa48("844") ? typeof phone === 'string' : stryMutAct_9fa48("843") ? false : (stryCov_9fa48("843", "844"), typeof phone !== (stryMutAct_9fa48("845") ? "" : (stryCov_9fa48("845"), 'string')))))) return stryMutAct_9fa48("846") ? true : (stryCov_9fa48("846"), false);
    const cleanPhone = phone.replace(stryMutAct_9fa48("848") ? /[\S\-().]/g : stryMutAct_9fa48("847") ? /[^\s\-().]/g : (stryCov_9fa48("847", "848"), /[\s\-().]/g), stryMutAct_9fa48("849") ? "Stryker was here!" : (stryCov_9fa48("849"), ''));
    return PHONE_REGEX.test(cleanPhone);
  }
}

/**
 * Validates phone for Mantine form validation.
 * @param value - The phone value
 * @returns Error message or null if valid
 */
export function validatePhone(value: string): string | null {
  if (stryMutAct_9fa48("850")) {
    {}
  } else {
    stryCov_9fa48("850");
    if (stryMutAct_9fa48("853") ? false : stryMutAct_9fa48("852") ? true : stryMutAct_9fa48("851") ? value : (stryCov_9fa48("851", "852", "853"), !value)) return null; // Phone is usually optional
    if (stryMutAct_9fa48("856") ? false : stryMutAct_9fa48("855") ? true : stryMutAct_9fa48("854") ? isValidPhone(value) : (stryCov_9fa48("854", "855", "856"), !isValidPhone(value))) return stryMutAct_9fa48("857") ? "" : (stryCov_9fa48("857"), 'Telefono invalido');
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
  if (stryMutAct_9fa48("858")) {
    {}
  } else {
    stryCov_9fa48("858");
    if (stryMutAct_9fa48("861") ? !cuit && typeof cuit !== 'string' : stryMutAct_9fa48("860") ? false : stryMutAct_9fa48("859") ? true : (stryCov_9fa48("859", "860", "861"), (stryMutAct_9fa48("862") ? cuit : (stryCov_9fa48("862"), !cuit)) || (stryMutAct_9fa48("864") ? typeof cuit === 'string' : stryMutAct_9fa48("863") ? false : (stryCov_9fa48("863", "864"), typeof cuit !== (stryMutAct_9fa48("865") ? "" : (stryCov_9fa48("865"), 'string')))))) return stryMutAct_9fa48("866") ? true : (stryCov_9fa48("866"), false);
    const cleanCUIT = cuit.replace(stryMutAct_9fa48("868") ? /[^\D]/g : stryMutAct_9fa48("867") ? /[\d]/g : (stryCov_9fa48("867", "868"), /[^\d]/g), stryMutAct_9fa48("869") ? "Stryker was here!" : (stryCov_9fa48("869"), ''));
    if (stryMutAct_9fa48("872") ? cleanCUIT.length === 11 : stryMutAct_9fa48("871") ? false : stryMutAct_9fa48("870") ? true : (stryCov_9fa48("870", "871", "872"), cleanCUIT.length !== 11)) return stryMutAct_9fa48("873") ? true : (stryCov_9fa48("873"), false);
    const weights = stryMutAct_9fa48("874") ? [] : (stryCov_9fa48("874"), [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]);
    let sum = 0;
    for (let i = 0; stryMutAct_9fa48("877") ? i >= 10 : stryMutAct_9fa48("876") ? i <= 10 : stryMutAct_9fa48("875") ? false : (stryCov_9fa48("875", "876", "877"), i < 10); stryMutAct_9fa48("878") ? i-- : (stryCov_9fa48("878"), i++)) {
      if (stryMutAct_9fa48("879")) {
        {}
      } else {
        stryCov_9fa48("879");
        stryMutAct_9fa48("880") ? sum -= Number.parseInt(cleanCUIT[i], 10) * weights[i] : (stryCov_9fa48("880"), sum += stryMutAct_9fa48("881") ? Number.parseInt(cleanCUIT[i], 10) / weights[i] : (stryCov_9fa48("881"), Number.parseInt(cleanCUIT[i], 10) * weights[i]));
      }
    }
    const checkDigit = Number.parseInt(cleanCUIT[10], 10);
    const calculatedCheckDigit = stryMutAct_9fa48("882") ? 11 + sum % 11 : (stryCov_9fa48("882"), 11 - (stryMutAct_9fa48("883") ? sum * 11 : (stryCov_9fa48("883"), sum % 11)));
    const finalDigit = (stryMutAct_9fa48("886") ? calculatedCheckDigit !== 11 : stryMutAct_9fa48("885") ? false : stryMutAct_9fa48("884") ? true : (stryCov_9fa48("884", "885", "886"), calculatedCheckDigit === 11)) ? 0 : (stryMutAct_9fa48("889") ? calculatedCheckDigit !== 10 : stryMutAct_9fa48("888") ? false : stryMutAct_9fa48("887") ? true : (stryCov_9fa48("887", "888", "889"), calculatedCheckDigit === 10)) ? 9 : calculatedCheckDigit;
    return stryMutAct_9fa48("892") ? checkDigit !== finalDigit : stryMutAct_9fa48("891") ? false : stryMutAct_9fa48("890") ? true : (stryCov_9fa48("890", "891", "892"), checkDigit === finalDigit);
  }
}

/**
 * Validates CUIT for Mantine form validation.
 * @param value - The CUIT value
 * @returns Error message or null if valid
 */
export function validateCUIT(value: string): string | null {
  if (stryMutAct_9fa48("893")) {
    {}
  } else {
    stryCov_9fa48("893");
    if (stryMutAct_9fa48("896") ? false : stryMutAct_9fa48("895") ? true : stryMutAct_9fa48("894") ? value : (stryCov_9fa48("894", "895", "896"), !value)) return stryMutAct_9fa48("897") ? "" : (stryCov_9fa48("897"), 'El CUIT es requerido');
    if (stryMutAct_9fa48("900") ? false : stryMutAct_9fa48("899") ? true : stryMutAct_9fa48("898") ? isValidCUIT(value) : (stryCov_9fa48("898", "899", "900"), !isValidCUIT(value))) return stryMutAct_9fa48("901") ? "" : (stryCov_9fa48("901"), 'CUIT invalido');
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
  if (stryMutAct_9fa48("902")) {
    {}
  } else {
    stryCov_9fa48("902");
    return (value: string) => {
      if (stryMutAct_9fa48("903")) {
        {}
      } else {
        stryCov_9fa48("903");
        if (stryMutAct_9fa48("907") ? value.length >= minLength : stryMutAct_9fa48("906") ? value.length <= minLength : stryMutAct_9fa48("905") ? false : stryMutAct_9fa48("904") ? true : (stryCov_9fa48("904", "905", "906", "907"), value.length < minLength)) {
          if (stryMutAct_9fa48("908")) {
            {}
          } else {
            stryCov_9fa48("908");
            return stryMutAct_9fa48("909") ? `` : (stryCov_9fa48("909"), `${fieldName} debe tener al menos ${minLength} caracteres`);
          }
        }
        if (stryMutAct_9fa48("913") ? value.length <= maxLength : stryMutAct_9fa48("912") ? value.length >= maxLength : stryMutAct_9fa48("911") ? false : stryMutAct_9fa48("910") ? true : (stryCov_9fa48("910", "911", "912", "913"), value.length > maxLength)) {
          if (stryMutAct_9fa48("914")) {
            {}
          } else {
            stryCov_9fa48("914");
            return stryMutAct_9fa48("915") ? `` : (stryCov_9fa48("915"), `${fieldName} no puede exceder ${maxLength} caracteres`);
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
export const validators = stryMutAct_9fa48("916") ? {} : (stryCov_9fa48("916"), {
  titulo: createLengthValidator(5, MAX_LENGTHS.TITULO, stryMutAct_9fa48("917") ? "" : (stryCov_9fa48("917"), 'El titulo')),
  descripcion: createLengthValidator(10, MAX_LENGTHS.DESCRIPCION, stryMutAct_9fa48("918") ? "" : (stryCov_9fa48("918"), 'La descripcion')),
  nombre: createLengthValidator(2, MAX_LENGTHS.NOMBRE, stryMutAct_9fa48("919") ? "" : (stryCov_9fa48("919"), 'El nombre')),
  resolucion: createLengthValidator(5, MAX_LENGTHS.RESOLUCION, stryMutAct_9fa48("920") ? "" : (stryCov_9fa48("920"), 'La resolucion'))
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
  if (stryMutAct_9fa48("921")) {
    {}
  } else {
    stryCov_9fa48("921");
    if (stryMutAct_9fa48("924") ? !url && typeof url !== 'string' : stryMutAct_9fa48("923") ? false : stryMutAct_9fa48("922") ? true : (stryCov_9fa48("922", "923", "924"), (stryMutAct_9fa48("925") ? url : (stryCov_9fa48("925"), !url)) || (stryMutAct_9fa48("927") ? typeof url === 'string' : stryMutAct_9fa48("926") ? false : (stryCov_9fa48("926", "927"), typeof url !== (stryMutAct_9fa48("928") ? "" : (stryCov_9fa48("928"), 'string')))))) return stryMutAct_9fa48("929") ? true : (stryCov_9fa48("929"), false);
    try {
      if (stryMutAct_9fa48("930")) {
        {}
      } else {
        stryCov_9fa48("930");
        const parsed = new URL(url);
        return stryMutAct_9fa48("933") ? parsed.protocol === 'http:' && parsed.protocol === 'https:' : stryMutAct_9fa48("932") ? false : stryMutAct_9fa48("931") ? true : (stryCov_9fa48("931", "932", "933"), (stryMutAct_9fa48("935") ? parsed.protocol !== 'http:' : stryMutAct_9fa48("934") ? false : (stryCov_9fa48("934", "935"), parsed.protocol === (stryMutAct_9fa48("936") ? "" : (stryCov_9fa48("936"), 'http:')))) || (stryMutAct_9fa48("938") ? parsed.protocol !== 'https:' : stryMutAct_9fa48("937") ? false : (stryCov_9fa48("937", "938"), parsed.protocol === (stryMutAct_9fa48("939") ? "" : (stryCov_9fa48("939"), 'https:')))));
      }
    } catch {
      if (stryMutAct_9fa48("940")) {
        {}
      } else {
        stryCov_9fa48("940");
        return stryMutAct_9fa48("941") ? true : (stryCov_9fa48("941"), false);
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
  if (stryMutAct_9fa48("942")) {
    {}
  } else {
    stryCov_9fa48("942");
    if (stryMutAct_9fa48("945") ? !url && typeof url !== 'string' : stryMutAct_9fa48("944") ? false : stryMutAct_9fa48("943") ? true : (stryCov_9fa48("943", "944", "945"), (stryMutAct_9fa48("946") ? url : (stryCov_9fa48("946"), !url)) || (stryMutAct_9fa48("948") ? typeof url === 'string' : stryMutAct_9fa48("947") ? false : (stryCov_9fa48("947", "948"), typeof url !== (stryMutAct_9fa48("949") ? "" : (stryCov_9fa48("949"), 'string')))))) return stryMutAct_9fa48("950") ? true : (stryCov_9fa48("950"), false);
    try {
      if (stryMutAct_9fa48("951")) {
        {}
      } else {
        stryCov_9fa48("951");
        // Allow template placeholders by temporarily replacing them
        const testUrl = url.replace(stryMutAct_9fa48("952") ? /\{[^xyz]\}/g : (stryCov_9fa48("952"), /\{[xyz]\}/g), stryMutAct_9fa48("953") ? "" : (stryCov_9fa48("953"), '0'));
        const parsed = new URL(testUrl);
        if (stryMutAct_9fa48("956") ? parsed.protocol === 'https:' : stryMutAct_9fa48("955") ? false : stryMutAct_9fa48("954") ? true : (stryCov_9fa48("954", "955", "956"), parsed.protocol !== (stryMutAct_9fa48("957") ? "" : (stryCov_9fa48("957"), 'https:')))) return stryMutAct_9fa48("958") ? true : (stryCov_9fa48("958"), false);

        // Check for required placeholders
        const hasPlaceholders = stryMutAct_9fa48("961") ? url.includes('{z}') && url.includes('{x}') || url.includes('{y}') : stryMutAct_9fa48("960") ? false : stryMutAct_9fa48("959") ? true : (stryCov_9fa48("959", "960", "961"), (stryMutAct_9fa48("963") ? url.includes('{z}') || url.includes('{x}') : stryMutAct_9fa48("962") ? true : (stryCov_9fa48("962", "963"), url.includes(stryMutAct_9fa48("964") ? "" : (stryCov_9fa48("964"), '{z}')) && url.includes(stryMutAct_9fa48("965") ? "" : (stryCov_9fa48("965"), '{x}')))) && url.includes(stryMutAct_9fa48("966") ? "" : (stryCov_9fa48("966"), '{y}')));
        return hasPlaceholders;
      }
    } catch {
      if (stryMutAct_9fa48("967")) {
        {}
      } else {
        stryCov_9fa48("967");
        return stryMutAct_9fa48("968") ? true : (stryCov_9fa48("968"), false);
      }
    }
  }
}