/**
 * Type declarations for @tabler/icons-react ESM modules.
 * These modules export Icon components directly from .mjs files
 * which don't have their own type declarations.
 */

declare module '@tabler/icons-react/dist/esm/icons/*.mjs' {
  import { Icon } from '@tabler/icons-react';
  const IconComponent: Icon;
  export default IconComponent;
}
