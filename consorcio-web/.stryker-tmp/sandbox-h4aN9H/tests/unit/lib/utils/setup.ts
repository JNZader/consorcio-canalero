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
 */
export const boundaryValues = [
  0,
  1,
  -1,
  Number.MAX_SAFE_INTEGER,
  Number.MIN_SAFE_INTEGER,
  0.5,
  -0.5,
  1.5,
  -1.5,
];

// ===========================================
// STRING VARIATIONS
// ===========================================

/**
 * Common string patterns for testing case conversion, trimming, and edge cases.
 */
export const commonStrings = [
  '',
  ' ',
  '  ',
  '\t',
  '\n',
  'hello',
  'HELLO',
  'HeLLo',
  'hello world',
  'HELLO WORLD',
  'special!@#$%chars',
  'números123',
  '  trimmed  ',
  '  spaces  on  both  ',
];

// ===========================================
// DATE VARIATIONS
// ===========================================

/**
 * Date instances for testing date formatting, comparison, and persistence.
 */
export const dateVariations = {
  now: new Date('2026-03-09T10:00:00Z'),
  yesterday: new Date('2026-03-08T10:00:00Z'),
  tomorrow: new Date('2026-03-10T10:00:00Z'),
  epoch: new Date('1970-01-01T00:00:00Z'),
  futureDate: new Date('2050-12-31T23:59:59Z'),
  pastDate: new Date('2000-01-01T00:00:00Z'),
};

// ===========================================
// EMAIL VALIDATION CASES
// ===========================================

/**
 * Test cases for email validation covering valid, invalid, and boundary conditions.
 */
export const emailTestCases = [
  // Valid emails
  { email: 'simple@example.com', isValid: true },
  { email: 'user+tag@example.co.uk', isValid: true },
  { email: 'test.email@sub.domain.com', isValid: true },
  { email: 'a@b.c', isValid: true },

  // Invalid emails
  { email: '', isValid: false },
  { email: 'plain', isValid: false },
  { email: '@example.com', isValid: false },
  { email: 'user@', isValid: false },
  { email: 'user @example.com', isValid: false },
  { email: 'user@example .com', isValid: false },
];

// ===========================================
// PHONE VALIDATION CASES
// ===========================================

/**
 * Test cases for phone number validation (Argentine format).
 */
export const phoneTestCases = [
  // Valid Argentine numbers
  { phone: '+541234567890', isValid: true },
  { phone: '541234567890', isValid: true },
  { phone: '01234567890', isValid: true },
  { phone: '1234567890', isValid: true },
  { phone: '+54 9 1234567890', isValid: true },

  // Invalid numbers
  { phone: '', isValid: false },
  { phone: '123', isValid: false },
  { phone: '000000000', isValid: false },
  { phone: 'abc', isValid: false },
];

// ===========================================
// OBJECT MERGE CASES
// ===========================================

/**
 * Test cases for shallow and deep object merging.
 */
export const mergeTestCases = [
  // Simple merge
  {
    a: { x: 1, y: 2 },
    b: { y: 3, z: 4 },
    expected: { x: 1, y: 3, z: 4 },
  },
  // Nested merge (shallow only)
  {
    a: { x: { nested: 1 } },
    b: { x: { nested: 2 } },
    expectedShallow: { x: { nested: 2 } },
  },
  // Empty objects
  {
    a: {},
    b: { x: 1 },
    expected: { x: 1 },
  },
  // Null/undefined values
  {
    a: { x: null },
    b: { x: undefined },
    expected: { x: undefined },
  },
];

// ===========================================
// CURRENCY FORMATTING CASES
// ===========================================

/**
 * Test cases for currency formatting with various amounts.
 */
export const currencyTestCases = [
  { amount: 1000, expected: '$1,000.00' },
  { amount: 1000.5, expected: '$1,000.50' },
  { amount: 0, expected: '$0.00' },
  { amount: 999999999, expected: '$999,999,999.00' },
  { amount: 0.01, expected: '$0.01' },
];

// ===========================================
// PAGINATION CASES
// ===========================================

/**
 * Test cases for pagination offset and limit calculations.
 */
export const paginationTestCases = [
  // Page 1
  { pageNumber: 0, pageSize: 10, expectedOffset: 0, expectedLimit: 10 },
  { pageNumber: 1, pageSize: 10, expectedOffset: 0, expectedLimit: 10 },
  // Page 2
  { pageNumber: 2, pageSize: 10, expectedOffset: 10, expectedLimit: 10 },
  // Different page sizes
  { pageNumber: 1, pageSize: 25, expectedOffset: 0, expectedLimit: 25 },
  { pageNumber: 2, pageSize: 25, expectedOffset: 25, expectedLimit: 25 },
  { pageNumber: 3, pageSize: 5, expectedOffset: 10, expectedLimit: 5 },
];

// ===========================================
// BOOLEAN EDGE CASES
// ===========================================

/**
 * Test cases for functions that handle truthy/falsy values.
 */
export const truthyFalsyValues = [
  true,
  false,
  0,
  1,
  '',
  'text',
  null,
  undefined,
  [],
  [1],
  {},
  { x: 1 },
  NaN,
];

// ===========================================
// TRUNCATE STRING CASES
// ===========================================

/**
 * Test cases for string truncation with various limits.
 */
export const truncateTestCases = [
  { text: 'hello world', limit: 5, expected: 'hello' },
  { text: 'hello', limit: 10, expected: 'hello' },
  { text: '', limit: 5, expected: '' },
  { text: 'exactly', limit: 7, expected: 'exactly' },
  { text: 'a bit longer text', limit: 8, expected: 'a bit lo' },
];

// ===========================================
// PERCENTAGE CALCULATION CASES
// ===========================================

/**
 * Test cases for percentage calculations (a / b * 100).
 */
export const percentageTestCases = [
  { a: 50, b: 100, expected: 50 },
  { a: 25, b: 100, expected: 25 },
  { a: 0, b: 100, expected: 0 },
  { a: 100, b: 100, expected: 100 },
];
