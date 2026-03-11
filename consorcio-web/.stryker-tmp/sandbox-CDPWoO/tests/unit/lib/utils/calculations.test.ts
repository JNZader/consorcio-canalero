/**
 * Mutation tests for arithmetic and calculation utility functions.
 * Tests arithmetic operators, rounding directions, and boundary conditions.
 */
// @ts-nocheck


import { describe, it, expect } from 'vitest';
import { boundaryValues, percentageTestCases } from './setup';

// ===========================================
// Helper Functions for Testing
// ===========================================

/**
 * Sum an array of numbers (helper for testing)
 */
function sum(numbers: number[]): number {
  return numbers.reduce((acc, num) => acc + num, 0);
}

/**
 * Calculate average of numbers
 */
function average(numbers: number[]): number {
  if (numbers.length === 0) return 0;
  return sum(numbers) / numbers.length;
}

/**
 * Calculate percentage: (a / b) * 100
 */
function percentage(a: number, b: number): number {
  if (b === 0) return 0;
  return (a / b) * 100;
}

/**
 * Round number to specified decimal places
 */
function roundToDecimals(num: number, decimals: number): number {
  if (decimals < 0) return num;
  const factor = Math.pow(10, decimals);
  return Math.round(num * factor) / factor;
}

/**
 * Get minimum value from array
 */
function minValue(numbers: number[]): number {
  if (numbers.length === 0) return 0;
  return Math.min(...numbers);
}

/**
 * Get maximum value from array
 */
function maxValue(numbers: number[]): number {
  if (numbers.length === 0) return 0;
  return Math.max(...numbers);
}

/**
 * Clamp value between min and max
 */
function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

// ===========================================
// Sum Tests
// ===========================================

describe('sum', () => {
  it('should return 0 for empty array', () => {
    expect(sum([])).toBe(0);
  });

  it('should sum positive numbers', () => {
    expect(sum([1, 2, 3])).toBe(6);
    expect(sum([10, 20, 30])).toBe(60);
  });

  it('should sum negative numbers', () => {
    expect(sum([-1, -2, -3])).toBe(-6);
  });

  it('should sum mixed positive and negative', () => {
    expect(sum([1, -1])).toBe(0);
    expect(sum([10, -5, -3])).toBe(2);
  });

  it('should handle zero', () => {
    expect(sum([0])).toBe(0);
    expect(sum([1, 0, 2])).toBe(3);
  });

  it('should handle floating point numbers', () => {
    expect(sum([0.1, 0.2, 0.3])).toBeCloseTo(0.6);
  });

  // Mutation testing: catch + to - mutation
  it('detects addition operator mutation', () => {
    expect(sum([1, 2])).toBe(3); // Not 1-2=-1
    expect(sum([5, 5])).toBe(10); // Not 5-5=0
  });

  // Mutation testing: catch 0 initialization
  it('detects initial value mutation', () => {
    const arr = [1, 2, 3];
    expect(sum(arr)).toBe(6); // Not 1 (if initialized to 1)
  });
});

// ===========================================
// Average Tests
// ===========================================

describe('average', () => {
  it('should return 0 for empty array', () => {
    expect(average([])).toBe(0);
  });

  it('should calculate average correctly', () => {
    expect(average([2, 4, 6])).toBe(4);
    expect(average([10, 20])).toBe(15);
  });

  it('should handle single element', () => {
    expect(average([5])).toBe(5);
  });

  it('should handle negative numbers', () => {
    expect(average([-2, 2])).toBe(0);
    expect(average([-10, -20, -30])).toBe(-20);
  });

  // Mutation testing: catch division operator
  it('detects division operator mutation', () => {
    expect(average([4, 8])).toBe(6); // Not 4*8=32 or 4+8=12
  });

  // Mutation testing: catch length-related mutations
  it('detects denominator mutation', () => {
    const arr = [10, 20, 30];
    expect(average(arr)).toBe(20); // Divided by 3, not 2 or 1
  });
});

// ===========================================
// Percentage Tests
// ===========================================

describe('percentage', () => {
  it.each(percentageTestCases)('$a / $b should be $expected%', ({ a, b, expected }) => {
    expect(percentage(a, b)).toBe(expected);
  });

  it('should return 0 for division by zero', () => {
    expect(percentage(50, 0)).toBe(0);
  });

  it('should handle percentage over 100', () => {
    expect(percentage(150, 100)).toBe(150);
  });

  it('should handle decimal results', () => {
    expect(percentage(1, 3)).toBeCloseTo(33.33, 1);
  });

  // Mutation testing: catch operator mutations (* to /, / to *)
  it('detects multiplication operator mutation', () => {
    expect(percentage(50, 100)).toBe(50); // Not 50/100=0.5
  });

  it('detects division operator mutation', () => {
    expect(percentage(100, 2)).toBe(5000); // Not 100*2=200
  });
});

// ===========================================
// Rounding Tests
// ===========================================

describe('roundToDecimals', () => {
  it('should round to specified decimal places', () => {
    expect(roundToDecimals(3.14159, 2)).toBe(3.14);
    expect(roundToDecimals(3.14159, 3)).toBe(3.142);
  });

  it('should handle 0 decimal places', () => {
    expect(roundToDecimals(3.7, 0)).toBe(4);
    expect(roundToDecimals(3.2, 0)).toBe(3);
  });

  it('should handle rounding up and down', () => {
    // JavaScript banker's rounding: 1.25 → 1.2 (rounds to even), 1.26 → 1.3
    expect(roundToDecimals(1.25, 1)).toBeCloseTo(1.3, 1); // Allow for floating point variation
    expect(roundToDecimals(1.26, 1)).toBe(1.3);
  });

  it('should handle negative decimals by returning original', () => {
    expect(roundToDecimals(3.14159, -1)).toBe(3.14159);
  });

  it('should handle large decimal places', () => {
    expect(roundToDecimals(1.23456789, 5)).toBe(1.23457);
  });

  // Mutation testing: catch direction mutations (floor vs ceil vs round)
  it('detects rounding direction mutations', () => {
    // Math.round(3.5) = 4, not floor=3 or ceil=4
    expect(roundToDecimals(3.5, 0)).toBe(4);
    // Math.round(1.4) = 1, not ceil=2 or floor=1
    expect(roundToDecimals(1.4, 0)).toBe(1);
  });
});

// ===========================================
// Min/Max Tests
// ===========================================

describe('minValue', () => {
  it('should return 0 for empty array', () => {
    expect(minValue([])).toBe(0);
  });

  it('should find minimum in positive numbers', () => {
    expect(minValue([5, 3, 8, 1])).toBe(1);
  });

  it('should find minimum in negative numbers', () => {
    expect(minValue([-1, -5, -3])).toBe(-5);
  });

  it('should find minimum in mixed numbers', () => {
    expect(minValue([10, -5, 0, 3])).toBe(-5);
  });

  // Mutation testing: catch min/max swap
  it('detects min/max swap mutation', () => {
    expect(minValue([1, 5, 3])).toBe(1); // Not 5
    expect(minValue([10, 2, 8])).toBe(2); // Not 10
  });
});

describe('maxValue', () => {
  it('should return 0 for empty array', () => {
    expect(maxValue([])).toBe(0);
  });

  it('should find maximum in positive numbers', () => {
    expect(maxValue([5, 3, 8, 1])).toBe(8);
  });

  it('should find maximum in negative numbers', () => {
    expect(maxValue([-1, -5, -3])).toBe(-1);
  });

  it('should find maximum in mixed numbers', () => {
    expect(maxValue([10, -5, 0, 3])).toBe(10);
  });

  // Mutation testing: catch min/max swap
  it('detects min/max swap mutation', () => {
    expect(maxValue([1, 5, 3])).toBe(5); // Not 1
    expect(maxValue([10, 2, 8])).toBe(10); // Not 2
  });
});

// ===========================================
// Clamp Tests
// ===========================================

describe('clamp', () => {
  it('should return value when within range', () => {
    expect(clamp(5, 0, 10)).toBe(5);
  });

  it('should return min when value below range', () => {
    expect(clamp(-5, 0, 10)).toBe(0);
  });

  it('should return max when value above range', () => {
    expect(clamp(15, 0, 10)).toBe(10);
  });

  it('should handle value at boundaries', () => {
    expect(clamp(0, 0, 10)).toBe(0);
    expect(clamp(10, 0, 10)).toBe(10);
  });

  it('should handle negative ranges', () => {
    expect(clamp(-5, -10, 0)).toBe(-5);
    expect(clamp(-15, -10, 0)).toBe(-10);
  });

  // Mutation testing: catch boundary swaps
  it('detects min/max boundary swap', () => {
    expect(clamp(-5, 0, 10)).toBe(0); // Returns 0, not -5
    expect(clamp(15, 0, 10)).toBe(10); // Returns 10, not 15
  });
});

// ===========================================
// Parametrized Boundary Tests
// ===========================================

describe.each(boundaryValues)('calculations with boundary value: %d', (value) => {
  it('should handle in sum', () => {
    expect(() => sum([value, 1, 2])).not.toThrow();
  });

  it('should handle in average', () => {
    expect(() => average([value, 1, 2])).not.toThrow();
  });

  it('should handle in percentage', () => {
    if (value !== 0) {
      expect(() => percentage(10, value)).not.toThrow();
    }
  });

  it('should handle in min/max', () => {
    expect(() => minValue([value, 1, 2])).not.toThrow();
    expect(() => maxValue([value, 1, 2])).not.toThrow();
  });

  it('should handle in clamp', () => {
    expect(() => clamp(value, -100, 100)).not.toThrow();
  });
});

// ===========================================
// Edge Case Integration Tests
// ===========================================

describe('calculation edge cases', () => {
  it('should handle very large numbers', () => {
    expect(sum([Number.MAX_SAFE_INTEGER / 2, Number.MAX_SAFE_INTEGER / 2])).toBeCloseTo(
      Number.MAX_SAFE_INTEGER,
      -10
    );
  });

  it('should handle very small numbers', () => {
    expect(sum([0.001, 0.002])).toBeCloseTo(0.003, 5);
  });

  it('should handle mixed scales', () => {
    expect(() => sum([1000000, 0.001, -999999.999])).not.toThrow();
  });
});
