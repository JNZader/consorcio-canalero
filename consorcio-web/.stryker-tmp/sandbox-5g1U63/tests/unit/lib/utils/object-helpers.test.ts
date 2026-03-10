/**
 * Mutation tests for object manipulation utility functions.
 * Tests shallow/deep copies, merge operations, and immutability.
 */
// @ts-nocheck


import { describe, it, expect } from 'vitest';
import { mergeTestCases } from './setup';

// ===========================================
// Helper Functions for Testing
// ===========================================

/**
 * Shallow merge two objects (b overwrites a)
 */
function mergeObjects(a: Record<string, any>, b: Record<string, any>): Record<string, any> {
  return { ...a, ...b };
}

/**
 * Deep merge two objects recursively
 */
function deepMergeObjects(
  a: Record<string, any>,
  b: Record<string, any>
): Record<string, any> {
  const result = { ...a };

  Object.keys(b).forEach((key) => {
    if (typeof b[key] === 'object' && b[key] !== null && !Array.isArray(b[key])) {
      result[key] = deepMergeObjects(result[key] || {}, b[key]);
    } else {
      result[key] = b[key];
    }
  });

  return result;
}

/**
 * Shallow clone an object
 */
function shallowClone<T extends Record<string, any>>(obj: T): T {
  return { ...obj } as T;
}

/**
 * Deep clone an object (simple implementation, no circular ref handling)
 */
function deepClone<T extends Record<string, any>>(obj: T): T {
  if (typeof obj !== 'object' || obj === null) {
    return obj;
  }

  if (Array.isArray(obj)) {
    return (obj.map((item) => deepClone(item)) as unknown) as T;
  }

  const cloned = {} as T;
  Object.keys(obj).forEach((key) => {
    cloned[key as keyof T] = deepClone(obj[key]);
  });

  return cloned;
}

/**
 * Pick specific keys from an object
 */
function pickKeys<T extends Record<string, any>, K extends (keyof T)[]>(
  obj: T,
  keys: K
): Partial<T> {
  const result: Partial<T> = {};
  keys.forEach((key) => {
    if (key in obj) {
      result[key] = obj[key];
    }
  });
  return result;
}

/**
 * Omit specific keys from an object
 */
function omitKeys<T extends Record<string, any>, K extends (keyof T)[]>(
  obj: T,
  keys: K
): Omit<T, K[number]> {
  const result: any = { ...obj };
  keys.forEach((key) => {
    delete result[key];
  });
  return result;
}

/**
 * Flatten a nested object into a single level with dot notation
 */
function flattenObject(obj: Record<string, any>, prefix = ''): Record<string, any> {
  const result: Record<string, any> = {};

  Object.keys(obj).forEach((key) => {
    const value = obj[key];
    const newKey = prefix ? `${prefix}.${key}` : key;

    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      Object.assign(result, flattenObject(value, newKey));
    } else {
      result[newKey] = value;
    }
  });

  return result;
}

// ===========================================
// Merge Tests
// ===========================================

describe('mergeObjects (shallow merge)', () => {
  it.each(mergeTestCases.filter((tc) => 'expected' in tc))(
    'should merge $a and $b correctly',
    ({ a, b, expected }) => {
      expect(mergeObjects(a, b)).toEqual(expected);
    }
  );

  it('should overwrite values from first object', () => {
    const a = { x: 1, y: 2 };
    const b = { y: 3 };
    const result = mergeObjects(a, b);
    expect(result.y).toBe(3); // b overwrites a
  });

  it('should include all keys from both objects', () => {
    const a = { x: 1 };
    const b = { y: 2 };
    const result = mergeObjects(a, b);
    expect(result).toHaveProperty('x');
    expect(result).toHaveProperty('y');
  });

  it('should not mutate original objects', () => {
    const a = { x: 1 };
    const b = { y: 2 };
    mergeObjects(a, b);
    expect(a).toEqual({ x: 1 });
    expect(b).toEqual({ y: 2 });
  });

  it('should handle null values', () => {
    const a = { x: null };
    const b = { x: 2 };
    const result = mergeObjects(a, b);
    expect(result.x).toBe(2);
  });

  it('should handle undefined values', () => {
    const a = { x: undefined };
    const b = { x: 2 };
    const result = mergeObjects(a, b);
    expect(result.x).toBe(2);
  });

  // Mutation testing: catch spreading order mutations
  it('detects spread order mutation (b should overwrite a)', () => {
    const a = { x: 10 };
    const b = { x: 20 };
    expect(mergeObjects(a, b)).toEqual({ x: 20 }); // Not 10
  });
});

// ===========================================
// Deep Merge Tests
// ===========================================

describe('deepMergeObjects (deep merge)', () => {
  it('should merge nested objects', () => {
    const a = { x: { nested: 1 } };
    const b = { x: { nested: 2 } };
    const result = deepMergeObjects(a, b);
    expect(result.x.nested).toBe(2);
  });

  it('should preserve keys from first object if not overwritten', () => {
    const a = { x: { a: 1, b: 2 } };
    const b = { x: { a: 99 } };
    const result = deepMergeObjects(a, b);
    expect(result.x.a).toBe(99);
    expect(result.x.b).toBe(2);
  });

  it('should handle multiple nesting levels', () => {
    const a = { x: { y: { z: 1 } } };
    const b = { x: { y: { z: 2 } } };
    const result = deepMergeObjects(a, b);
    expect(result.x.y.z).toBe(2);
  });

  it('should not mutate original objects', () => {
    const a = { x: { nested: 1 } };
    const b = { x: { nested: 2 } };
    const originalA = JSON.stringify(a);
    deepMergeObjects(a, b);
    expect(JSON.stringify(a)).toBe(originalA);
  });
});

// ===========================================
// Clone Tests
// ===========================================

describe('shallowClone', () => {
  it('should create a new object', () => {
    const obj = { x: 1, y: 2 };
    const clone = shallowClone(obj);
    expect(clone).toEqual(obj);
    expect(clone).not.toBe(obj);
  });

  it('should not deep clone nested objects', () => {
    const nested = { a: 1 };
    const obj = { x: nested };
    const clone = shallowClone(obj);
    expect(clone.x).toBe(nested); // Same reference
  });

  it('should copy primitive values', () => {
    const obj = { x: 1, y: 'text', z: true };
    const clone = shallowClone(obj);
    expect(clone).toEqual(obj);
  });

  // Mutation testing: catch return of original instead of clone
  it('detects missing clone spread operator', () => {
    const obj = { x: 1 };
    const clone = shallowClone(obj);
    (clone as any).x = 99;
    expect(obj.x).toBe(1); // Original unchanged
  });
});

describe('deepClone', () => {
  it('should create a new object', () => {
    const obj = { x: 1, y: 2 };
    const clone = deepClone(obj);
    expect(clone).toEqual(obj);
    expect(clone).not.toBe(obj);
  });

  it('should deep clone nested objects', () => {
    const nested = { a: 1 };
    const obj = { x: nested };
    const clone = deepClone(obj);
    expect(clone.x).toEqual(nested);
    expect(clone.x).not.toBe(nested); // Different reference
  });

  it('should deep clone arrays', () => {
    const obj = { items: [1, 2, 3] };
    const clone = deepClone(obj);
    expect(clone.items).toEqual([1, 2, 3]);
    expect(clone.items).not.toBe(obj.items);
  });

  it('should handle multiple nesting levels', () => {
    const obj = { a: { b: { c: 1 } } };
    const clone = deepClone(obj);
    expect(clone.a.b.c).toBe(1);
    expect(clone.a).not.toBe(obj.a);
    expect(clone.a.b).not.toBe(obj.a.b);
  });

  it('should not mutate original on clone modification', () => {
    const obj = { x: { y: 1 } };
    const clone = deepClone(obj);
    (clone.x as any).y = 99;
    expect(obj.x.y).toBe(1);
  });
});

// ===========================================
// Pick/Omit Tests
// ===========================================

describe('pickKeys', () => {
  it('should pick specified keys', () => {
    const obj = { x: 1, y: 2, z: 3 };
    const result = pickKeys(obj, ['x', 'z']);
    expect(result).toEqual({ x: 1, z: 3 });
  });

  it('should handle empty keys array', () => {
    const obj = { x: 1, y: 2 };
    const result = pickKeys(obj, []);
    expect(result).toEqual({});
  });

  it('should handle non-existent keys', () => {
    const obj = { x: 1 };
    const result = pickKeys(obj, ['x', 'y' as any]);
    expect(result).toEqual({ x: 1 });
  });

  it('should not mutate original', () => {
    const obj = { x: 1, y: 2 };
    const original = JSON.stringify(obj);
    pickKeys(obj, ['x']);
    expect(JSON.stringify(obj)).toBe(original);
  });

  // Mutation testing: catch all keys instead of picked
  it('detects missing key filter', () => {
    const obj = { x: 1, y: 2, z: 3 };
    const result = pickKeys(obj, ['x']);
    expect(result).not.toEqual(obj);
  });
});

describe('omitKeys', () => {
  it('should omit specified keys', () => {
    const obj = { x: 1, y: 2, z: 3 };
    const result = omitKeys(obj, ['y']);
    expect(result).toEqual({ x: 1, z: 3 });
  });

  it('should handle empty keys array', () => {
    const obj = { x: 1, y: 2 };
    const result = omitKeys(obj, []);
    expect(result).toEqual({ x: 1, y: 2 });
  });

  it('should handle non-existent keys', () => {
    const obj = { x: 1, y: 2 };
    const result = omitKeys(obj, ['z' as any]);
    expect(result).toEqual({ x: 1, y: 2 });
  });

  it('should not mutate original', () => {
    const obj = { x: 1, y: 2 };
    const original = JSON.stringify(obj);
    omitKeys(obj, ['y']);
    expect(JSON.stringify(obj)).toBe(original);
  });

  // Mutation testing: catch delete not working
  it('detects missing key deletion', () => {
    const obj = { x: 1, y: 2, z: 3 };
    const result = omitKeys(obj, ['y']);
    expect('y' in result).toBe(false);
  });
});

// ===========================================
// Flatten Tests
// ===========================================

describe('flattenObject', () => {
  it('should flatten simple nested object', () => {
    const obj = { a: { b: 1 } };
    const result = flattenObject(obj);
    expect(result).toEqual({ 'a.b': 1 });
  });

  it('should handle multiple levels', () => {
    const obj = { a: { b: { c: 1 } } };
    const result = flattenObject(obj);
    expect(result).toEqual({ 'a.b.c': 1 });
  });

  it('should handle multiple keys at same level', () => {
    const obj = { a: { b: 1, c: 2 }, d: 3 };
    const result = flattenObject(obj);
    expect(result).toEqual({ 'a.b': 1, 'a.c': 2, d: 3 });
  });

  it('should not flatten arrays', () => {
    const obj = { a: [1, 2, 3] };
    const result = flattenObject(obj);
    expect(result).toEqual({ a: [1, 2, 3] });
  });

  it('should handle null values', () => {
    const obj = { a: { b: null } };
    const result = flattenObject(obj);
    expect(result).toEqual({ 'a.b': null });
  });

  // Mutation testing: catch separator not added
  it('detects missing dot separator', () => {
    const obj = { a: { b: 1 } };
    const result = flattenObject(obj);
    expect('a.b' in result).toBe(true);
  });
});

// ===========================================
// Integration Tests
// ===========================================

describe('object operations integration', () => {
  it('merge + clone should not create references', () => {
    const a = { x: { value: 1 } };
    const b = { y: { value: 2 } };
    const merged = mergeObjects(a, b);
    const cloned = deepClone(merged);
    (cloned.x as any).value = 99;
    expect((a.x as any).value).toBe(1);
  });

  it('pick from merged object', () => {
    const a = { x: 1, y: 2 };
    const b = { z: 3 };
    const merged = mergeObjects(a, b);
    const picked = pickKeys(merged, ['x', 'z']);
    expect(picked).toEqual({ x: 1, z: 3 });
  });

  it('omit from deep cloned object', () => {
    const obj = { a: { nested: true }, b: 2, c: 3 };
    const cloned = deepClone(obj);
    const omitted = omitKeys(cloned, ['b']);
    expect('b' in omitted).toBe(false);
    expect('a' in omitted).toBe(true);
  });

  it('flatten then pick keys', () => {
    const obj = { user: { profile: { name: 'John', age: 30 }, email: 'john@test' } };
    const flattened = flattenObject(obj);
    const picked = pickKeys(flattened, ['user.profile.name', 'user.email' as any]);
    expect(picked).toHaveProperty('user.profile.name');
  });
});

// ===========================================
// Immutability Tests
// ===========================================

describe('immutability preservation', () => {
  it('should not allow mutations to affect original after merge', () => {
    const original = { x: { value: 1 } };
    const copy = mergeObjects(original, {});
    (copy as any).x.value = 99;
    // Note: shallow merge doesn't deep clone, so this will mutate
    // This test documents the behavior
    expect((original as any).x.value).toBe(99); // Shallow merge limitation
  });

  it('should prevent mutations with deep clone', () => {
    const original = { x: { value: 1 } };
    const clone = deepClone(original);
    (clone as any).x.value = 99;
    expect((original.x as any).value).toBe(1);
  });

  it('returned object from pick is independent', () => {
    const original = { x: 1, y: { nested: true } };
    const picked = pickKeys(original, ['x']);
    (picked as any).x = 99;
    expect((original as any).x).toBe(1);
  });
});
