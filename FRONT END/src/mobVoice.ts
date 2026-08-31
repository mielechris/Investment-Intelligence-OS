import type { LivingCastKey } from "./livingCast";
import {
  v76AmbientLine,
  v76ReactionLine,
  v76ReplayBannerLine,
  type V76DialogueContext,
} from "./dialogueEngineV76";

/**
 * Backward-compatible voice facade.
 *
 * V7.6 keeps the existing mobVoice API so V7.2/V7.3/V7.4 presentation
 * components automatically inherit the richer character engine without
 * changing any persisted IIOS state, model output, approval, or execution.
 */
export type MobVoiceContext = V76DialogueContext;

export function mobReactionLine(key: LivingCastKey, context: MobVoiceContext): string {
  return v76ReactionLine(key, context);
}

export function mobAmbientLine(key: LivingCastKey): string {
  return v76AmbientLine(key);
}

export function mobReplayBannerLine(ticker: string, eventType: string): string {
  return v76ReplayBannerLine(ticker, eventType);
}
