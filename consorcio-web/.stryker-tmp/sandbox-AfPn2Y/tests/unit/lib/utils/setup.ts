/**
 * Test fixtures and parametrization helpers for utility function testing.
 * Provides reusable test data sets for boundary value analysis and mutation testing.
 */
// @ts-nocheck


// ===========================================
// NUMERIC BOUNDARIES
// ===========================================

/**
 * Boundary numeric values for testing arithmetic operations and limits.
 * Includes zero, one, negative, and JavaScript safe integer boundaries.
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
export const boundaryValues = stryMutAct_9fa48("352") ? [] : (stryCov_9fa48("352"), [0, 1, stryMutAct_9fa48("353") ? +1 : (stryCov_9fa48("353"), -1), Number.MAX_SAFE_INTEGER, Number.MIN_SAFE_INTEGER, 0.5, stryMutAct_9fa48("354") ? +0.5 : (stryCov_9fa48("354"), -0.5), 1.5, stryMutAct_9fa48("355") ? +1.5 : (stryCov_9fa48("355"), -1.5)]);

// ===========================================
// STRING VARIATIONS
// ===========================================

/**
 * Common string patterns for testing case conversion, trimming, and edge cases.
 */
export const commonStrings = stryMutAct_9fa48("356") ? [] : (stryCov_9fa48("356"), [stryMutAct_9fa48("357") ? "Stryker was here!" : (stryCov_9fa48("357"), ''), stryMutAct_9fa48("358") ? "" : (stryCov_9fa48("358"), ' '), stryMutAct_9fa48("359") ? "" : (stryCov_9fa48("359"), '  '), stryMutAct_9fa48("360") ? "" : (stryCov_9fa48("360"), '\t'), stryMutAct_9fa48("361") ? "" : (stryCov_9fa48("361"), '\n'), stryMutAct_9fa48("362") ? "" : (stryCov_9fa48("362"), 'hello'), stryMutAct_9fa48("363") ? "" : (stryCov_9fa48("363"), 'HELLO'), stryMutAct_9fa48("364") ? "" : (stryCov_9fa48("364"), 'HeLLo'), stryMutAct_9fa48("365") ? "" : (stryCov_9fa48("365"), 'hello world'), stryMutAct_9fa48("366") ? "" : (stryCov_9fa48("366"), 'HELLO WORLD'), stryMutAct_9fa48("367") ? "" : (stryCov_9fa48("367"), 'special!@#$%chars'), stryMutAct_9fa48("368") ? "" : (stryCov_9fa48("368"), 'números123'), stryMutAct_9fa48("369") ? "" : (stryCov_9fa48("369"), '  trimmed  '), stryMutAct_9fa48("370") ? "" : (stryCov_9fa48("370"), '  spaces  on  both  ')]);

// ===========================================
// DATE VARIATIONS
// ===========================================

/**
 * Date instances for testing date formatting, comparison, and persistence.
 */
export const dateVariations = stryMutAct_9fa48("371") ? {} : (stryCov_9fa48("371"), {
  now: new Date(stryMutAct_9fa48("372") ? "" : (stryCov_9fa48("372"), '2026-03-09T10:00:00Z')),
  yesterday: new Date(stryMutAct_9fa48("373") ? "" : (stryCov_9fa48("373"), '2026-03-08T10:00:00Z')),
  tomorrow: new Date(stryMutAct_9fa48("374") ? "" : (stryCov_9fa48("374"), '2026-03-10T10:00:00Z')),
  epoch: new Date(stryMutAct_9fa48("375") ? "" : (stryCov_9fa48("375"), '1970-01-01T00:00:00Z')),
  futureDate: new Date(stryMutAct_9fa48("376") ? "" : (stryCov_9fa48("376"), '2050-12-31T23:59:59Z')),
  pastDate: new Date(stryMutAct_9fa48("377") ? "" : (stryCov_9fa48("377"), '2000-01-01T00:00:00Z'))
});

// ===========================================
// EMAIL VALIDATION CASES
// ===========================================

/**
 * Test cases for email validation covering valid, invalid, and boundary conditions.
 */
export const emailTestCases = stryMutAct_9fa48("378") ? [] : (stryCov_9fa48("378"), [// Valid emails
stryMutAct_9fa48("379") ? {} : (stryCov_9fa48("379"), {
  email: stryMutAct_9fa48("380") ? "" : (stryCov_9fa48("380"), 'simple@example.com'),
  isValid: stryMutAct_9fa48("381") ? false : (stryCov_9fa48("381"), true)
}), stryMutAct_9fa48("382") ? {} : (stryCov_9fa48("382"), {
  email: stryMutAct_9fa48("383") ? "" : (stryCov_9fa48("383"), 'user+tag@example.co.uk'),
  isValid: stryMutAct_9fa48("384") ? false : (stryCov_9fa48("384"), true)
}), stryMutAct_9fa48("385") ? {} : (stryCov_9fa48("385"), {
  email: stryMutAct_9fa48("386") ? "" : (stryCov_9fa48("386"), 'test.email@sub.domain.com'),
  isValid: stryMutAct_9fa48("387") ? false : (stryCov_9fa48("387"), true)
}), stryMutAct_9fa48("388") ? {} : (stryCov_9fa48("388"), {
  email: stryMutAct_9fa48("389") ? "" : (stryCov_9fa48("389"), 'a@b.c'),
  isValid: stryMutAct_9fa48("390") ? false : (stryCov_9fa48("390"), true)
}), // Invalid emails
stryMutAct_9fa48("391") ? {} : (stryCov_9fa48("391"), {
  email: stryMutAct_9fa48("392") ? "Stryker was here!" : (stryCov_9fa48("392"), ''),
  isValid: stryMutAct_9fa48("393") ? true : (stryCov_9fa48("393"), false)
}), stryMutAct_9fa48("394") ? {} : (stryCov_9fa48("394"), {
  email: stryMutAct_9fa48("395") ? "" : (stryCov_9fa48("395"), 'plain'),
  isValid: stryMutAct_9fa48("396") ? true : (stryCov_9fa48("396"), false)
}), stryMutAct_9fa48("397") ? {} : (stryCov_9fa48("397"), {
  email: stryMutAct_9fa48("398") ? "" : (stryCov_9fa48("398"), '@example.com'),
  isValid: stryMutAct_9fa48("399") ? true : (stryCov_9fa48("399"), false)
}), stryMutAct_9fa48("400") ? {} : (stryCov_9fa48("400"), {
  email: stryMutAct_9fa48("401") ? "" : (stryCov_9fa48("401"), 'user@'),
  isValid: stryMutAct_9fa48("402") ? true : (stryCov_9fa48("402"), false)
}), stryMutAct_9fa48("403") ? {} : (stryCov_9fa48("403"), {
  email: stryMutAct_9fa48("404") ? "" : (stryCov_9fa48("404"), 'user @example.com'),
  isValid: stryMutAct_9fa48("405") ? true : (stryCov_9fa48("405"), false)
}), stryMutAct_9fa48("406") ? {} : (stryCov_9fa48("406"), {
  email: stryMutAct_9fa48("407") ? "" : (stryCov_9fa48("407"), 'user@example .com'),
  isValid: stryMutAct_9fa48("408") ? true : (stryCov_9fa48("408"), false)
})]);

// ===========================================
// PHONE VALIDATION CASES
// ===========================================

/**
 * Test cases for phone number validation (Argentine format).
 */
export const phoneTestCases = stryMutAct_9fa48("409") ? [] : (stryCov_9fa48("409"), [// Valid Argentine numbers
stryMutAct_9fa48("410") ? {} : (stryCov_9fa48("410"), {
  phone: stryMutAct_9fa48("411") ? "" : (stryCov_9fa48("411"), '+541234567890'),
  isValid: stryMutAct_9fa48("412") ? false : (stryCov_9fa48("412"), true)
}), stryMutAct_9fa48("413") ? {} : (stryCov_9fa48("413"), {
  phone: stryMutAct_9fa48("414") ? "" : (stryCov_9fa48("414"), '541234567890'),
  isValid: stryMutAct_9fa48("415") ? false : (stryCov_9fa48("415"), true)
}), stryMutAct_9fa48("416") ? {} : (stryCov_9fa48("416"), {
  phone: stryMutAct_9fa48("417") ? "" : (stryCov_9fa48("417"), '01234567890'),
  isValid: stryMutAct_9fa48("418") ? false : (stryCov_9fa48("418"), true)
}), stryMutAct_9fa48("419") ? {} : (stryCov_9fa48("419"), {
  phone: stryMutAct_9fa48("420") ? "" : (stryCov_9fa48("420"), '1234567890'),
  isValid: stryMutAct_9fa48("421") ? false : (stryCov_9fa48("421"), true)
}), stryMutAct_9fa48("422") ? {} : (stryCov_9fa48("422"), {
  phone: stryMutAct_9fa48("423") ? "" : (stryCov_9fa48("423"), '+54 9 1234567890'),
  isValid: stryMutAct_9fa48("424") ? false : (stryCov_9fa48("424"), true)
}), // Invalid numbers
stryMutAct_9fa48("425") ? {} : (stryCov_9fa48("425"), {
  phone: stryMutAct_9fa48("426") ? "Stryker was here!" : (stryCov_9fa48("426"), ''),
  isValid: stryMutAct_9fa48("427") ? true : (stryCov_9fa48("427"), false)
}), stryMutAct_9fa48("428") ? {} : (stryCov_9fa48("428"), {
  phone: stryMutAct_9fa48("429") ? "" : (stryCov_9fa48("429"), '123'),
  isValid: stryMutAct_9fa48("430") ? true : (stryCov_9fa48("430"), false)
}), stryMutAct_9fa48("431") ? {} : (stryCov_9fa48("431"), {
  phone: stryMutAct_9fa48("432") ? "" : (stryCov_9fa48("432"), '000000000'),
  isValid: stryMutAct_9fa48("433") ? true : (stryCov_9fa48("433"), false)
}), stryMutAct_9fa48("434") ? {} : (stryCov_9fa48("434"), {
  phone: stryMutAct_9fa48("435") ? "" : (stryCov_9fa48("435"), 'abc'),
  isValid: stryMutAct_9fa48("436") ? true : (stryCov_9fa48("436"), false)
})]);

// ===========================================
// OBJECT MERGE CASES
// ===========================================

/**
 * Test cases for shallow and deep object merging.
 */
export const mergeTestCases = stryMutAct_9fa48("437") ? [] : (stryCov_9fa48("437"), [// Simple merge
stryMutAct_9fa48("438") ? {} : (stryCov_9fa48("438"), {
  a: stryMutAct_9fa48("439") ? {} : (stryCov_9fa48("439"), {
    x: 1,
    y: 2
  }),
  b: stryMutAct_9fa48("440") ? {} : (stryCov_9fa48("440"), {
    y: 3,
    z: 4
  }),
  expected: stryMutAct_9fa48("441") ? {} : (stryCov_9fa48("441"), {
    x: 1,
    y: 3,
    z: 4
  })
}), // Nested merge (shallow only)
stryMutAct_9fa48("442") ? {} : (stryCov_9fa48("442"), {
  a: stryMutAct_9fa48("443") ? {} : (stryCov_9fa48("443"), {
    x: stryMutAct_9fa48("444") ? {} : (stryCov_9fa48("444"), {
      nested: 1
    })
  }),
  b: stryMutAct_9fa48("445") ? {} : (stryCov_9fa48("445"), {
    x: stryMutAct_9fa48("446") ? {} : (stryCov_9fa48("446"), {
      nested: 2
    })
  }),
  expectedShallow: stryMutAct_9fa48("447") ? {} : (stryCov_9fa48("447"), {
    x: stryMutAct_9fa48("448") ? {} : (stryCov_9fa48("448"), {
      nested: 2
    })
  })
}), // Empty objects
stryMutAct_9fa48("449") ? {} : (stryCov_9fa48("449"), {
  a: {},
  b: stryMutAct_9fa48("450") ? {} : (stryCov_9fa48("450"), {
    x: 1
  }),
  expected: stryMutAct_9fa48("451") ? {} : (stryCov_9fa48("451"), {
    x: 1
  })
}), // Null/undefined values
stryMutAct_9fa48("452") ? {} : (stryCov_9fa48("452"), {
  a: stryMutAct_9fa48("453") ? {} : (stryCov_9fa48("453"), {
    x: null
  }),
  b: stryMutAct_9fa48("454") ? {} : (stryCov_9fa48("454"), {
    x: undefined
  }),
  expected: stryMutAct_9fa48("455") ? {} : (stryCov_9fa48("455"), {
    x: undefined
  })
})]);

// ===========================================
// CURRENCY FORMATTING CASES
// ===========================================

/**
 * Test cases for currency formatting with various amounts.
 */
export const currencyTestCases = stryMutAct_9fa48("456") ? [] : (stryCov_9fa48("456"), [stryMutAct_9fa48("457") ? {} : (stryCov_9fa48("457"), {
  amount: 1000,
  expected: stryMutAct_9fa48("458") ? "" : (stryCov_9fa48("458"), '$1,000.00')
}), stryMutAct_9fa48("459") ? {} : (stryCov_9fa48("459"), {
  amount: 1000.5,
  expected: stryMutAct_9fa48("460") ? "" : (stryCov_9fa48("460"), '$1,000.50')
}), stryMutAct_9fa48("461") ? {} : (stryCov_9fa48("461"), {
  amount: 0,
  expected: stryMutAct_9fa48("462") ? "" : (stryCov_9fa48("462"), '$0.00')
}), stryMutAct_9fa48("463") ? {} : (stryCov_9fa48("463"), {
  amount: 999999999,
  expected: stryMutAct_9fa48("464") ? "" : (stryCov_9fa48("464"), '$999,999,999.00')
}), stryMutAct_9fa48("465") ? {} : (stryCov_9fa48("465"), {
  amount: 0.01,
  expected: stryMutAct_9fa48("466") ? "" : (stryCov_9fa48("466"), '$0.01')
})]);

// ===========================================
// PAGINATION CASES
// ===========================================

/**
 * Test cases for pagination offset and limit calculations.
 */
export const paginationTestCases = stryMutAct_9fa48("467") ? [] : (stryCov_9fa48("467"), [// Page 1
stryMutAct_9fa48("468") ? {} : (stryCov_9fa48("468"), {
  pageNumber: 0,
  pageSize: 10,
  expectedOffset: 0,
  expectedLimit: 10
}), stryMutAct_9fa48("469") ? {} : (stryCov_9fa48("469"), {
  pageNumber: 1,
  pageSize: 10,
  expectedOffset: 0,
  expectedLimit: 10
}), // Page 2
stryMutAct_9fa48("470") ? {} : (stryCov_9fa48("470"), {
  pageNumber: 2,
  pageSize: 10,
  expectedOffset: 10,
  expectedLimit: 10
}), // Different page sizes
stryMutAct_9fa48("471") ? {} : (stryCov_9fa48("471"), {
  pageNumber: 1,
  pageSize: 25,
  expectedOffset: 0,
  expectedLimit: 25
}), stryMutAct_9fa48("472") ? {} : (stryCov_9fa48("472"), {
  pageNumber: 2,
  pageSize: 25,
  expectedOffset: 25,
  expectedLimit: 25
}), stryMutAct_9fa48("473") ? {} : (stryCov_9fa48("473"), {
  pageNumber: 3,
  pageSize: 5,
  expectedOffset: 10,
  expectedLimit: 5
})]);

// ===========================================
// BOOLEAN EDGE CASES
// ===========================================

/**
 * Test cases for functions that handle truthy/falsy values.
 */
export const truthyFalsyValues = stryMutAct_9fa48("474") ? [] : (stryCov_9fa48("474"), [stryMutAct_9fa48("475") ? false : (stryCov_9fa48("475"), true), stryMutAct_9fa48("476") ? true : (stryCov_9fa48("476"), false), 0, 1, stryMutAct_9fa48("477") ? "Stryker was here!" : (stryCov_9fa48("477"), ''), stryMutAct_9fa48("478") ? "" : (stryCov_9fa48("478"), 'text'), null, undefined, stryMutAct_9fa48("479") ? ["Stryker was here"] : (stryCov_9fa48("479"), []), stryMutAct_9fa48("480") ? [] : (stryCov_9fa48("480"), [1]), {}, stryMutAct_9fa48("481") ? {} : (stryCov_9fa48("481"), {
  x: 1
}), NaN]);

// ===========================================
// TRUNCATE STRING CASES
// ===========================================

/**
 * Test cases for string truncation with various limits.
 */
export const truncateTestCases = stryMutAct_9fa48("482") ? [] : (stryCov_9fa48("482"), [stryMutAct_9fa48("483") ? {} : (stryCov_9fa48("483"), {
  text: stryMutAct_9fa48("484") ? "" : (stryCov_9fa48("484"), 'hello world'),
  limit: 5,
  expected: stryMutAct_9fa48("485") ? "" : (stryCov_9fa48("485"), 'hello')
}), stryMutAct_9fa48("486") ? {} : (stryCov_9fa48("486"), {
  text: stryMutAct_9fa48("487") ? "" : (stryCov_9fa48("487"), 'hello'),
  limit: 10,
  expected: stryMutAct_9fa48("488") ? "" : (stryCov_9fa48("488"), 'hello')
}), stryMutAct_9fa48("489") ? {} : (stryCov_9fa48("489"), {
  text: stryMutAct_9fa48("490") ? "Stryker was here!" : (stryCov_9fa48("490"), ''),
  limit: 5,
  expected: stryMutAct_9fa48("491") ? "Stryker was here!" : (stryCov_9fa48("491"), '')
}), stryMutAct_9fa48("492") ? {} : (stryCov_9fa48("492"), {
  text: stryMutAct_9fa48("493") ? "" : (stryCov_9fa48("493"), 'exactly'),
  limit: 7,
  expected: stryMutAct_9fa48("494") ? "" : (stryCov_9fa48("494"), 'exactly')
}), stryMutAct_9fa48("495") ? {} : (stryCov_9fa48("495"), {
  text: stryMutAct_9fa48("496") ? "" : (stryCov_9fa48("496"), 'a bit longer text'),
  limit: 8,
  expected: stryMutAct_9fa48("497") ? "" : (stryCov_9fa48("497"), 'a bit lo')
})]);

// ===========================================
// PERCENTAGE CALCULATION CASES
// ===========================================

/**
 * Test cases for percentage calculations (a / b * 100).
 */
export const percentageTestCases = stryMutAct_9fa48("498") ? [] : (stryCov_9fa48("498"), [stryMutAct_9fa48("499") ? {} : (stryCov_9fa48("499"), {
  a: 50,
  b: 100,
  expected: 50
}), stryMutAct_9fa48("500") ? {} : (stryCov_9fa48("500"), {
  a: 25,
  b: 100,
  expected: 25
}), stryMutAct_9fa48("501") ? {} : (stryCov_9fa48("501"), {
  a: 0,
  b: 100,
  expected: 0
}), stryMutAct_9fa48("502") ? {} : (stryCov_9fa48("502"), {
  a: 100,
  b: 100,
  expected: 100
})]);