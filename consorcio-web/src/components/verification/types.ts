/**
 * Shared types for verification components.
 *
 * `VerificationMethod` / `isVerificationMethod` vivian aca para elegir entre
 * Google y magic link. Con el magic link retirado (B2-2.5) Google es la unica
 * via, asi que un tipo que sigue validando `'email'` como metodo legitimo seria
 * una mentira: se borraron junto con el flujo. Si algun dia entra un segundo
 * metodo, se reescribe con el contexto de ese metodo, no con el del que se fue.
 */

export interface VerificationFormErrors {
  contacto_email?: string;
}
