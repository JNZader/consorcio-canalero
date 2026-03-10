/**
 * Shared formatting utilities for the Consorcio Canalero application.
 */
// @ts-nocheck


/**
 * Get month format based on format type (avoids nested ternary).
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
function getMonthFormat(format: 'short' | 'medium' | 'long'): '2-digit' | 'short' | 'long' {
  if (stryMutAct_9fa48("0")) {
    {}
  } else {
    stryCov_9fa48("0");
    if (stryMutAct_9fa48("3") ? format !== 'short' : stryMutAct_9fa48("2") ? false : stryMutAct_9fa48("1") ? true : (stryCov_9fa48("1", "2", "3"), format === (stryMutAct_9fa48("4") ? "" : (stryCov_9fa48("4"), 'short')))) return stryMutAct_9fa48("5") ? "" : (stryCov_9fa48("5"), '2-digit');
    if (stryMutAct_9fa48("8") ? format !== 'long' : stryMutAct_9fa48("7") ? false : stryMutAct_9fa48("6") ? true : (stryCov_9fa48("6", "7", "8"), format === (stryMutAct_9fa48("9") ? "" : (stryCov_9fa48("9"), 'long')))) return stryMutAct_9fa48("10") ? "" : (stryCov_9fa48("10"), 'long');
    return stryMutAct_9fa48("11") ? "" : (stryCov_9fa48("11"), 'short');
  }
}

/**
 * Format a date string or Date object to a localized Spanish date string.
 * @param date - The date to format (string, Date, or null/undefined)
 * @param options - Additional formatting options
 * @returns Formatted date string or fallback value
 */
export function formatDate(date: string | Date | null | undefined, options: {
  includeTime?: boolean;
  fallback?: string;
  format?: 'short' | 'medium' | 'long';
} = {}): string {
  if (stryMutAct_9fa48("12")) {
    {}
  } else {
    stryCov_9fa48("12");
    const {
      includeTime = stryMutAct_9fa48("13") ? true : (stryCov_9fa48("13"), false),
      fallback = stryMutAct_9fa48("14") ? "" : (stryCov_9fa48("14"), '-'),
      format = stryMutAct_9fa48("15") ? "" : (stryCov_9fa48("15"), 'medium')
    } = options;
    if (stryMutAct_9fa48("18") ? false : stryMutAct_9fa48("17") ? true : stryMutAct_9fa48("16") ? date : (stryCov_9fa48("16", "17", "18"), !date)) return fallback;
    try {
      if (stryMutAct_9fa48("19")) {
        {}
      } else {
        stryCov_9fa48("19");
        const dateObj = (stryMutAct_9fa48("22") ? typeof date !== 'string' : stryMutAct_9fa48("21") ? false : stryMutAct_9fa48("20") ? true : (stryCov_9fa48("20", "21", "22"), typeof date === (stryMutAct_9fa48("23") ? "" : (stryCov_9fa48("23"), 'string')))) ? new Date(date) : date;
        if (stryMutAct_9fa48("25") ? false : stryMutAct_9fa48("24") ? true : (stryCov_9fa48("24", "25"), Number.isNaN(dateObj.getTime()))) return fallback;
        const dateOptions: Intl.DateTimeFormatOptions = stryMutAct_9fa48("26") ? {} : (stryCov_9fa48("26"), {
          year: stryMutAct_9fa48("27") ? "" : (stryCov_9fa48("27"), 'numeric'),
          month: getMonthFormat(format),
          day: stryMutAct_9fa48("28") ? "" : (stryCov_9fa48("28"), 'numeric')
        });
        if (stryMutAct_9fa48("30") ? false : stryMutAct_9fa48("29") ? true : (stryCov_9fa48("29", "30"), includeTime)) {
          if (stryMutAct_9fa48("31")) {
            {}
          } else {
            stryCov_9fa48("31");
            dateOptions.hour = stryMutAct_9fa48("32") ? "" : (stryCov_9fa48("32"), '2-digit');
            dateOptions.minute = stryMutAct_9fa48("33") ? "" : (stryCov_9fa48("33"), '2-digit');
          }
        }
        return dateObj.toLocaleDateString(stryMutAct_9fa48("34") ? "" : (stryCov_9fa48("34"), 'es-AR'), dateOptions);
      }
    } catch {
      if (stryMutAct_9fa48("35")) {
        {}
      } else {
        stryCov_9fa48("35");
        return fallback;
      }
    }
  }
}

/**
 * Format a date for input fields (YYYY-MM-DD format).
 * @param date - The date to format
 * @returns Date string in YYYY-MM-DD format
 */
export function formatDateForInput(date: Date | string | null | undefined): string {
  if (stryMutAct_9fa48("36")) {
    {}
  } else {
    stryCov_9fa48("36");
    if (stryMutAct_9fa48("39") ? false : stryMutAct_9fa48("38") ? true : stryMutAct_9fa48("37") ? date : (stryCov_9fa48("37", "38", "39"), !date)) return stryMutAct_9fa48("40") ? "Stryker was here!" : (stryCov_9fa48("40"), '');
    try {
      if (stryMutAct_9fa48("41")) {
        {}
      } else {
        stryCov_9fa48("41");
        const dateObj = (stryMutAct_9fa48("44") ? typeof date !== 'string' : stryMutAct_9fa48("43") ? false : stryMutAct_9fa48("42") ? true : (stryCov_9fa48("42", "43", "44"), typeof date === (stryMutAct_9fa48("45") ? "" : (stryCov_9fa48("45"), 'string')))) ? new Date(date) : date;
        if (stryMutAct_9fa48("47") ? false : stryMutAct_9fa48("46") ? true : (stryCov_9fa48("46", "47"), Number.isNaN(dateObj.getTime()))) return stryMutAct_9fa48("48") ? "Stryker was here!" : (stryCov_9fa48("48"), '');
        return dateObj.toISOString().split(stryMutAct_9fa48("49") ? "" : (stryCov_9fa48("49"), 'T'))[0];
      }
    } catch {
      if (stryMutAct_9fa48("50")) {
        {}
      } else {
        stryCov_9fa48("50");
        return stryMutAct_9fa48("51") ? "Stryker was here!" : (stryCov_9fa48("51"), '');
      }
    }
  }
}

/**
 * Format a relative time string (e.g., "hace 2 horas").
 * @param date - The date to format
 * @returns Relative time string in Spanish
 */
export function formatRelativeTime(date: string | Date | null | undefined): string {
  if (stryMutAct_9fa48("52")) {
    {}
  } else {
    stryCov_9fa48("52");
    if (stryMutAct_9fa48("55") ? false : stryMutAct_9fa48("54") ? true : stryMutAct_9fa48("53") ? date : (stryCov_9fa48("53", "54", "55"), !date)) return stryMutAct_9fa48("56") ? "" : (stryCov_9fa48("56"), '-');
    try {
      if (stryMutAct_9fa48("57")) {
        {}
      } else {
        stryCov_9fa48("57");
        const dateObj = (stryMutAct_9fa48("60") ? typeof date !== 'string' : stryMutAct_9fa48("59") ? false : stryMutAct_9fa48("58") ? true : (stryCov_9fa48("58", "59", "60"), typeof date === (stryMutAct_9fa48("61") ? "" : (stryCov_9fa48("61"), 'string')))) ? new Date(date) : date;
        if (stryMutAct_9fa48("63") ? false : stryMutAct_9fa48("62") ? true : (stryCov_9fa48("62", "63"), Number.isNaN(dateObj.getTime()))) return stryMutAct_9fa48("64") ? "" : (stryCov_9fa48("64"), '-');
        const now = new Date();
        const diffMs = stryMutAct_9fa48("65") ? now.getTime() + dateObj.getTime() : (stryCov_9fa48("65"), now.getTime() - dateObj.getTime());
        const diffMins = Math.floor(stryMutAct_9fa48("66") ? diffMs * 60000 : (stryCov_9fa48("66"), diffMs / 60000));
        const diffHours = Math.floor(stryMutAct_9fa48("67") ? diffMins * 60 : (stryCov_9fa48("67"), diffMins / 60));
        const diffDays = Math.floor(stryMutAct_9fa48("68") ? diffHours * 24 : (stryCov_9fa48("68"), diffHours / 24));
        if (stryMutAct_9fa48("72") ? diffMins >= 1 : stryMutAct_9fa48("71") ? diffMins <= 1 : stryMutAct_9fa48("70") ? false : stryMutAct_9fa48("69") ? true : (stryCov_9fa48("69", "70", "71", "72"), diffMins < 1)) return stryMutAct_9fa48("73") ? "" : (stryCov_9fa48("73"), 'Ahora mismo');
        if (stryMutAct_9fa48("77") ? diffMins >= 60 : stryMutAct_9fa48("76") ? diffMins <= 60 : stryMutAct_9fa48("75") ? false : stryMutAct_9fa48("74") ? true : (stryCov_9fa48("74", "75", "76", "77"), diffMins < 60)) return stryMutAct_9fa48("78") ? `` : (stryCov_9fa48("78"), `Hace ${diffMins} ${(stryMutAct_9fa48("81") ? diffMins !== 1 : stryMutAct_9fa48("80") ? false : stryMutAct_9fa48("79") ? true : (stryCov_9fa48("79", "80", "81"), diffMins === 1)) ? stryMutAct_9fa48("82") ? "" : (stryCov_9fa48("82"), 'minuto') : stryMutAct_9fa48("83") ? "" : (stryCov_9fa48("83"), 'minutos')}`);
        if (stryMutAct_9fa48("87") ? diffHours >= 24 : stryMutAct_9fa48("86") ? diffHours <= 24 : stryMutAct_9fa48("85") ? false : stryMutAct_9fa48("84") ? true : (stryCov_9fa48("84", "85", "86", "87"), diffHours < 24)) return stryMutAct_9fa48("88") ? `` : (stryCov_9fa48("88"), `Hace ${diffHours} ${(stryMutAct_9fa48("91") ? diffHours !== 1 : stryMutAct_9fa48("90") ? false : stryMutAct_9fa48("89") ? true : (stryCov_9fa48("89", "90", "91"), diffHours === 1)) ? stryMutAct_9fa48("92") ? "" : (stryCov_9fa48("92"), 'hora') : stryMutAct_9fa48("93") ? "" : (stryCov_9fa48("93"), 'horas')}`);
        if (stryMutAct_9fa48("97") ? diffDays >= 7 : stryMutAct_9fa48("96") ? diffDays <= 7 : stryMutAct_9fa48("95") ? false : stryMutAct_9fa48("94") ? true : (stryCov_9fa48("94", "95", "96", "97"), diffDays < 7)) return stryMutAct_9fa48("98") ? `` : (stryCov_9fa48("98"), `Hace ${diffDays} ${(stryMutAct_9fa48("101") ? diffDays !== 1 : stryMutAct_9fa48("100") ? false : stryMutAct_9fa48("99") ? true : (stryCov_9fa48("99", "100", "101"), diffDays === 1)) ? stryMutAct_9fa48("102") ? "" : (stryCov_9fa48("102"), 'dia') : stryMutAct_9fa48("103") ? "" : (stryCov_9fa48("103"), 'dias')}`);
        return formatDate(dateObj, stryMutAct_9fa48("104") ? {} : (stryCov_9fa48("104"), {
          format: stryMutAct_9fa48("105") ? "" : (stryCov_9fa48("105"), 'medium')
        }));
      }
    } catch {
      if (stryMutAct_9fa48("106")) {
        {}
      } else {
        stryCov_9fa48("106");
        return stryMutAct_9fa48("107") ? "" : (stryCov_9fa48("107"), '-');
      }
    }
  }
}

/**
 * Format a number with thousands separators.
 * @param value - The number to format
 * @param decimals - Number of decimal places
 * @returns Formatted number string
 */
export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (stryMutAct_9fa48("108")) {
    {}
  } else {
    stryCov_9fa48("108");
    if (stryMutAct_9fa48("111") ? value === null && value === undefined : stryMutAct_9fa48("110") ? false : stryMutAct_9fa48("109") ? true : (stryCov_9fa48("109", "110", "111"), (stryMutAct_9fa48("113") ? value !== null : stryMutAct_9fa48("112") ? false : (stryCov_9fa48("112", "113"), value === null)) || (stryMutAct_9fa48("115") ? value !== undefined : stryMutAct_9fa48("114") ? false : (stryCov_9fa48("114", "115"), value === undefined)))) return stryMutAct_9fa48("116") ? "" : (stryCov_9fa48("116"), '-');
    return value.toLocaleString(stryMutAct_9fa48("117") ? "" : (stryCov_9fa48("117"), 'es-AR'), stryMutAct_9fa48("118") ? {} : (stryCov_9fa48("118"), {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    }));
  }
}

/**
 * Format hectares with proper suffix.
 * @param value - The value in hectares
 * @returns Formatted string with "ha" suffix
 */
export function formatHectares(value: number | null | undefined): string {
  if (stryMutAct_9fa48("119")) {
    {}
  } else {
    stryCov_9fa48("119");
    if (stryMutAct_9fa48("122") ? value === null && value === undefined : stryMutAct_9fa48("121") ? false : stryMutAct_9fa48("120") ? true : (stryCov_9fa48("120", "121", "122"), (stryMutAct_9fa48("124") ? value !== null : stryMutAct_9fa48("123") ? false : (stryCov_9fa48("123", "124"), value === null)) || (stryMutAct_9fa48("126") ? value !== undefined : stryMutAct_9fa48("125") ? false : (stryCov_9fa48("125", "126"), value === undefined)))) return stryMutAct_9fa48("127") ? "" : (stryCov_9fa48("127"), '-');
    return stryMutAct_9fa48("128") ? `` : (stryCov_9fa48("128"), `${formatNumber(value)} ha`);
  }
}

/**
 * Format a percentage value.
 * @param value - The percentage value (0-100)
 * @param decimals - Number of decimal places
 * @returns Formatted percentage string
 */
export function formatPercentage(value: number | null | undefined, decimals = 1): string {
  if (stryMutAct_9fa48("129")) {
    {}
  } else {
    stryCov_9fa48("129");
    if (stryMutAct_9fa48("132") ? value === null && value === undefined : stryMutAct_9fa48("131") ? false : stryMutAct_9fa48("130") ? true : (stryCov_9fa48("130", "131", "132"), (stryMutAct_9fa48("134") ? value !== null : stryMutAct_9fa48("133") ? false : (stryCov_9fa48("133", "134"), value === null)) || (stryMutAct_9fa48("136") ? value !== undefined : stryMutAct_9fa48("135") ? false : (stryCov_9fa48("135", "136"), value === undefined)))) return stryMutAct_9fa48("137") ? "" : (stryCov_9fa48("137"), '-');
    return stryMutAct_9fa48("138") ? `` : (stryCov_9fa48("138"), `${formatNumber(value, decimals)}%`);
  }
}

/**
 * Format a date with custom options for display.
 * @param date - The date to format
 * @param options - Intl.DateTimeFormatOptions to use
 * @returns Formatted date string
 */
export function formatDateCustom(date: string | Date | null | undefined, options: Intl.DateTimeFormatOptions, fallback = stryMutAct_9fa48("139") ? "" : (stryCov_9fa48("139"), '-')): string {
  if (stryMutAct_9fa48("140")) {
    {}
  } else {
    stryCov_9fa48("140");
    if (stryMutAct_9fa48("143") ? false : stryMutAct_9fa48("142") ? true : stryMutAct_9fa48("141") ? date : (stryCov_9fa48("141", "142", "143"), !date)) return fallback;
    try {
      if (stryMutAct_9fa48("144")) {
        {}
      } else {
        stryCov_9fa48("144");
        const dateObj = (stryMutAct_9fa48("147") ? typeof date !== 'string' : stryMutAct_9fa48("146") ? false : stryMutAct_9fa48("145") ? true : (stryCov_9fa48("145", "146", "147"), typeof date === (stryMutAct_9fa48("148") ? "" : (stryCov_9fa48("148"), 'string')))) ? new Date(date) : date;
        if (stryMutAct_9fa48("150") ? false : stryMutAct_9fa48("149") ? true : (stryCov_9fa48("149", "150"), Number.isNaN(dateObj.getTime()))) return fallback;
        return dateObj.toLocaleDateString(stryMutAct_9fa48("151") ? "" : (stryCov_9fa48("151"), 'es-AR'), options);
      }
    } catch {
      if (stryMutAct_9fa48("152")) {
        {}
      } else {
        stryCov_9fa48("152");
        return fallback;
      }
    }
  }
}

/**
 * Format a date with time for display.
 * @param date - The date to format
 * @returns Formatted date and time string
 */
export function formatDateTime(date: string | Date | null | undefined, fallback = stryMutAct_9fa48("153") ? "" : (stryCov_9fa48("153"), '-')): string {
  if (stryMutAct_9fa48("154")) {
    {}
  } else {
    stryCov_9fa48("154");
    if (stryMutAct_9fa48("157") ? false : stryMutAct_9fa48("156") ? true : stryMutAct_9fa48("155") ? date : (stryCov_9fa48("155", "156", "157"), !date)) return fallback;
    try {
      if (stryMutAct_9fa48("158")) {
        {}
      } else {
        stryCov_9fa48("158");
        const dateObj = (stryMutAct_9fa48("161") ? typeof date !== 'string' : stryMutAct_9fa48("160") ? false : stryMutAct_9fa48("159") ? true : (stryCov_9fa48("159", "160", "161"), typeof date === (stryMutAct_9fa48("162") ? "" : (stryCov_9fa48("162"), 'string')))) ? new Date(date) : date;
        if (stryMutAct_9fa48("164") ? false : stryMutAct_9fa48("163") ? true : (stryCov_9fa48("163", "164"), Number.isNaN(dateObj.getTime()))) return fallback;
        return dateObj.toLocaleString(stryMutAct_9fa48("165") ? "" : (stryCov_9fa48("165"), 'es-AR'));
      }
    } catch {
      if (stryMutAct_9fa48("166")) {
        {}
      } else {
        stryCov_9fa48("166");
        return fallback;
      }
    }
  }
}