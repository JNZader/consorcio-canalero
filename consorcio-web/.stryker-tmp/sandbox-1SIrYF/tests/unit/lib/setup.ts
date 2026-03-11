/**
 * Parametrization fixtures for Phase 1 mutation tests
 * These fixtures provide edge cases, boundary values, and common test patterns
 */
// @ts-nocheck


// ===========================================
// BOUNDARY VALUES
// ===========================================

export const boundaryValues = {
  numbers: [
    0,
    1,
    -1,
    Number.MAX_SAFE_INTEGER,
    Number.MIN_SAFE_INTEGER,
    0.5,
    -0.5,
    Infinity,
    -Infinity,
  ],
  nullishValues: [null, undefined],
  arrayLengths: {
    empty: [],
    single: [1],
    multiple: [1, 2, 3, 4, 5],
  },
};

// ===========================================
// COMMON STRINGS
// ===========================================

export const commonStrings = {
  empty: '',
  whitespace: ' ',
  multipleSpaces: '   ',
  trimmed: 'normal',
  uppercase: 'UPPERCASE',
  lowercase: 'lowercase',
  mixedCase: 'MixedCase',
  withTrimmed: '  trimmed  ',
  numbers: '12345',
  special: '!@#$%^&*()',
  unicode: '中文テスト',
  nullishValues: [null, undefined] as const,
};

// ===========================================
// DATE VARIATIONS
// ===========================================

export const dateVariations = {
  valid: {
    epoch: new Date('1970-01-01'),
    y2k: new Date('2000-01-01'),
    recent: new Date('2024-03-15'),  // Use mid-month to avoid timezone issues
    today: new Date(),
    withTime: new Date('2024-03-10T14:30:45'),
  },
  strings: {
    isoString: '2024-01-15T00:00:00Z',  // Use mid-month to avoid timezone issues
    dateOnly: '2024-01-01',
    invalidString: 'invalid-date',
    emptyString: '',
  },
  invalid: {
    nullValue: null,
    undefinedValue: undefined,
    invalidString: 'not-a-date',
  },
};

// ===========================================
// EMAIL TEST CASES
// ===========================================

export const emailTestCases = {
  valid: [
    'user@example.com',
    'test.user@example.co.uk',
    'user+tag@example.com',
    'user_name@example.com',
    'user-name@example.com',
    '123@example.com',
    'a@b.c',
    'user..name@example.com', // EMAIL_REGEX accepts consecutive dots in local part
    'user@example', // Valid per EMAIL_REGEX (domain without TLD)
  ],
  invalid: [
    'plaintext',
    '@example.com',
    'user@',
    'user @example.com',
    'user@.com',
    '',
    ' ',
  ],
  edgeCases: {
    tooLong: 'a'.repeat(255) + '@example.com', // Exceeds MAX_EMAIL_LENGTH
    specialChars: 'user+special!@example.com',
    numbers: '123456789@example.com',
    singleChar: 'a@b.co',
  },
  nullish: [null, undefined],
};

// ===========================================
// PHONE TEST CASES
// ===========================================

export const phoneTestCases = {
  valid: [
    '+541123456789',
    '541123456789',
    '01123456789',
    '1123456789',
    '+54 9 11 2345 6789',
    '011-2345-6789',
    '+54-11-2345-6789',
    '011 2345 6789',  // spaces are stripped
  ],
  invalid: [
    '123', // Too short
    '01234567', // Too short
    '0123456789abc', // Contains letters
    '+55 11 9 8765 4321', // Wrong country code
    'abcdefghijk', // Only letters
    '+54 (011) 2345-6789', // Parentheses not in strip regex - still has '()' after strip
    '',
    ' ',
  ],
  edgeCases: {
    withParens: '(011) 2345-6789',
    withDots: '011.2345.6789',
    spaces: '011 2345 6789',
    leadingZeros: '00541123456789',
  },
  nullish: [null, undefined],
};

// ===========================================
// URL TEST CASES
// ===========================================

export const urlTestCases = {
  valid: {
    http: 'http://example.com',
    https: 'https://example.com',
    withPath: 'https://example.com/path/to/page',
    withQuery: 'https://example.com/path?key=value&foo=bar',
    withFragment: 'https://example.com/path#section',
    withPort: 'https://example.com:8443/path',
    withAuth: 'https://user:pass@example.com',
    complex: 'https://subdomain.example.co.uk:8443/path?query=value#hash',
  },
  invalid: [
    'not-a-url',
    'ftp://example.com', // Wrong protocol
    '://example.com',
    'http://',
    'https://',
    '',
    ' ',
    'javascript:alert("xss")', // XSS attempt
  ],
  edgeCases: {
    localhost: 'http://localhost:3000',
    ipAddress: 'https://192.168.1.1',
    noTld: 'https://localhost',
  },
  nullish: [null, undefined],
};

// ===========================================
// TILE URL TEST CASES
// ===========================================

export const tileUrlTestCases = {
  valid: [
    'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    'https://example.com/tiles/{z}/{x}/{y}.png',
  ],
  invalid: [
    'http://example.com/{z}/{x}/{y}.png', // Not HTTPS
    'https://example.com/{z}/{x}', // Missing {y}
    'https://example.com/{z}/{y}', // Missing {x}
    'https://example.com/{x}/{y}', // Missing {z}
    'https://example.com/tiles/tile.png', // No placeholders
    'ftp://example.com/{z}/{x}/{y}.png', // Wrong protocol
    '',
    ' ',
  ],
  edgeCases: {
    lowercase: 'https://example.com/{z}/{x}/{y}.png',
    uppercase: 'https://example.com/{Z}/{X}/{Y}.png', // Different case
    mixedFormat: 'https://example.com/z{z}x{x}y{y}.png',
  },
  nullish: [null, undefined],
};

// ===========================================
// CUIT TEST CASES
// ===========================================

export const cuitTestCases = {
  valid: [
    '20-123-456-786', // Valid CUIT with dashes
    '20123456786', // Without dashes
    '27-123-456-780', // Another valid format
    '00000000000', // All zeros - mathematically valid per check digit algorithm
  ],
  invalid: [
    '12345678901', // Invalid check digit
    '11111111111', // All ones - mathematically invalid
    '20-12345678-0', // Wrong format
    '123', // Too short
    '123456789012', // Too long
    'abcdefghijk', // Non-numeric
    '',
    ' ',
  ],
  edgeCases: {
    withSpaces: '20 123 456 786',
    withDashes: '20-123-456-786',
    startWithZero: '20-000-000-069', // Calculated valid check digit
  },
  nullish: [null, undefined],
};

// ===========================================
// RELATIVE TIME TEST CASES
// ===========================================

export const relativeTimeTestCases = {
  times: {
    justNow: new Date(Date.now() - 10 * 1000), // 10 seconds ago
    oneMinuteAgo: new Date(Date.now() - 60 * 1000),
    fiveMinutesAgo: new Date(Date.now() - 5 * 60 * 1000),
    oneHourAgo: new Date(Date.now() - 60 * 60 * 1000),
    threeHoursAgo: new Date(Date.now() - 3 * 60 * 60 * 1000),
    oneDayAgo: new Date(Date.now() - 24 * 60 * 60 * 1000),
    threeDaysAgo: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000),
    sixDaysAgo: new Date(Date.now() - 6 * 24 * 60 * 60 * 1000),
    eightDaysAgo: new Date(Date.now() - 8 * 24 * 60 * 60 * 1000),
  },
  strings: {
    isoString: new Date().toISOString(),
  },
  invalid: [
    'invalid-date-string',
    null,
    undefined,
  ],
};

// ===========================================
// NUMBER FORMATTING TEST CASES
// ===========================================

export const numberFormattingTestCases = {
  valid: [
    { value: 0, decimals: 0, expected: '0' },
    { value: 1, decimals: 0, expected: '1' },
    { value: 1000, decimals: 0, expected: '1.000' }, // Spanish uses . for thousands
    { value: 1000.5, decimals: 1, expected: '1.000,5' },
    { value: 0.1, decimals: 1, expected: '0,1' },
    { value: -1000, decimals: 0, expected: '-1.000' },
    { value: Number.MAX_SAFE_INTEGER, decimals: 0, expected: '9.007.199.254.740.991' },
  ],
  nullish: [null, undefined],
};

// ===========================================
// PERCENTAGE FORMATTING TEST CASES
// ===========================================

export const percentageFormattingTestCases = {
  valid: [
    { value: 0, decimals: 0, expected: '0%' },
    { value: 50, decimals: 1, expected: '50,0%' },
    { value: 33.333, decimals: 2, expected: '33,33%' },
    { value: 100, decimals: 0, expected: '100%' },
  ],
  nullish: [null, undefined],
};

// ===========================================
// HECTARES FORMATTING TEST CASES
// ===========================================

export const hectaresFormattingTestCases = {
  valid: [
    { value: 0, expected: '0 ha' },
    { value: 100, expected: '100 ha' },
    { value: 1000, expected: '1.000 ha' },
    { value: 1000.5, expected: '1.001 ha' }, // Rounded to 0 decimals by default
  ],
  nullish: [null, undefined],
};

// ===========================================
// USER ROLE TEST CASES
// ===========================================

export const userRoleTestCases = {
  valid: ['ciudadano', 'operador', 'admin'],
  invalid: ['superadmin', 'guest', 'user', '', 'Admin', 'ADMIN', null, undefined],
};

// ===========================================
// USUARIO TYPE GUARD TEST CASES
// ===========================================

export const usuarioTestCases = {
  valid: [
    {
      id: 'user-123',
      email: 'user@example.com',
      rol: 'ciudadano',
      nombre: 'John Doe',
      telefono: '1123456789',
    },
    {
      id: 'admin-1',
      email: 'admin@example.com',
      rol: 'admin',
      nombre: null,
      telefono: null,
    },
    {
      id: 'op-1',
      email: 'operator@example.com',
      rol: 'operador',
    },
  ],
  invalid: [
    { email: 'user@example.com', rol: 'ciudadano' }, // Missing id
    { id: '', email: 'user@example.com', rol: 'ciudadano' }, // Empty id
    { id: 'user-1', email: 'user@example.com', rol: 'invalid' }, // Invalid role
    { id: 'user-1', email: 'user@example.com', rol: 'ciudadano', nombre: 123 }, // Invalid nombre type
    { id: 'user-1', email: 'user@example.com', rol: 'ciudadano', telefono: [] }, // Invalid telefono type
    null,
    undefined,
    'not-an-object',
  ],
};

// ===========================================
// LAYER STYLE TEST CASES
// ===========================================

export const layerStyleTestCases = {
  valid: [
    {
      color: '#3388ff',
      weight: 2,
      fillColor: '#3388ff',
      fillOpacity: 0.1,
    },
    {
      color: 'red',
      weight: 3,
      fillColor: 'blue',
      fillOpacity: 1,
    },
    {
      color: 'rgb(255, 0, 0)',
      weight: 0,
      fillColor: 'rgba(0, 0, 255, 0.5)',
      fillOpacity: 0.5,
    },
  ],
  invalid: [
    { color: '#fff', weight: 2 }, // Missing fillColor and fillOpacity
    { color: '#fff', weight: 'thick', fillColor: '#fff', fillOpacity: 0.5 }, // Invalid weight type
    { color: '#fff', weight: 2, fillColor: '#fff', fillOpacity: 1.5 }, // fillOpacity > 1
    { color: '#fff', weight: 2, fillColor: '#fff', fillOpacity: -0.1 }, // fillOpacity < 0
    null,
    undefined,
    'not-an-object',
  ],
};

// ===========================================
// SELECTED IMAGE TEST CASES
// ===========================================

export const selectedImageTestCases = {
  valid: {
    basic: {
      tile_url: 'https://earthengine.googleapis.com/tiles/z{z}x{x}y{y}',
      target_date: '2024-01-01',
      sensor: 'Sentinel-2',
      visualization: 'RGB',
      visualization_description: 'True color',
      collection: 'COPERNICUS/S2',
      images_count: 10,
      selected_at: new Date().toISOString(),
    },
    withFloodInfo: {
      tile_url: 'https://earthengine.googleapis.com/tiles/z{z}x{x}y{y}',
      target_date: '2024-01-01',
      sensor: 'Sentinel-1',
      visualization: 'VV',
      visualization_description: 'SAR backscatter',
      collection: 'COPERNICUS/S1',
      images_count: 5,
      selected_at: new Date().toISOString(),
      flood_info: {
        id: 'flood-123',
        name: 'Test Flood',
        description: 'Test flooding area',
        severity: 'high',
      },
    },
  },
  invalid: [
    { /* Missing required fields */ },
    { tile_url: '', target_date: '2024-01-01', sensor: 'Sentinel-2' }, // Empty tile_url
    { tile_url: 'http://example.com/{z}/{x}/{y}', target_date: '2024-01-01', sensor: 'Sentinel-2' }, // HTTP not HTTPS
    { tile_url: 'https://example.com/{z}/{x}/{y}', target_date: '2024-01-01', sensor: 'Sentinel-2' }, // Non-Earth Engine URL
    { tile_url: 'https://earthengine.googleapis.com/{z}/{x}/{y}', target_date: '2024-01-01', sensor: 'Sentinel-2', images_count: -1 }, // Negative count
    null,
    undefined,
  ],
};

// ===========================================
// GEOMETRY TEST CASES
// ===========================================

export const geometryTestCases = {
  valid: {
    point: { type: 'Point', coordinates: [0, 0] },
    lineString: { type: 'LineString', coordinates: [[0, 0], [1, 1]] },
    polygon: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]] },
    multiPoint: { type: 'MultiPoint', coordinates: [[0, 0], [1, 1]] },
    multiLineString: { type: 'MultiLineString', coordinates: [[[0, 0], [1, 1]], [[2, 2], [3, 3]]] },
    multiPolygon: { type: 'MultiPolygon', coordinates: [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]] },
    geometryCollection: { type: 'GeometryCollection', geometries: [{ type: 'Point', coordinates: [0, 0] }] },
  },
  invalid: [
    { type: 'InvalidType', coordinates: [] },
    { type: 'Point' }, // Missing coordinates
    { type: 'Point', coordinates: 'not-array' },
    { type: 'GeometryCollection', coordinates: [] }, // Wrong field
    { type: 'GeometryCollection', geometries: 'not-array' },
    null,
    undefined,
  ],
};
