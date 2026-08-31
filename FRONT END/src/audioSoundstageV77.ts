import type { LivingCastKey } from "./livingCast";
import type { V76RoomKey } from "./dialogueEngineV76";

export type V77VoiceProfile = {
  label: string;
  rate: number;
  pitch: number;
  preferredVoiceHints: string[];
  delivery: string;
};

export const V77_VOICE_PROFILES: Record<LivingCastKey, V77VoiceProfile> = {
  max: {
    label: "Boss Baritone",
    rate: 0.88,
    pitch: 0.72,
    preferredVoiceHints: ["Daniel", "Alex", "Fred", "Reed", "Aaron"],
    delivery: "Low, slow, final. Sounds like the meeting ends when he says it ends.",
  },
  policy: {
    label: "Consigliere Dry Read",
    rate: 0.92,
    pitch: 0.9,
    preferredVoiceHints: ["Daniel", "Alex", "Reed", "Eddy"],
    delivery: "Measured and suspicious, like he already found the clause nobody wanted him to find.",
  },
  macro: {
    label: "Rates Desk Fast Talk",
    rate: 1.08,
    pitch: 0.96,
    preferredVoiceHints: ["Aaron", "Eddy", "Alex", "Reed"],
    delivery: "Quick, annoyed, analytical. Bips before feelings.",
  },
  fundamentals: {
    label: "Cash-Flow Heavyweight",
    rate: 0.96,
    pitch: 0.78,
    preferredVoiceHints: ["Fred", "Alex", "Daniel", "Reed"],
    delivery: "Blunt and heavy. Every sentence sounds like somebody owes him a margin bridge.",
  },
  market_structure: {
    label: "Tape Desk Street Read",
    rate: 1.04,
    pitch: 0.92,
    preferredVoiceHints: ["Eddy", "Aaron", "Alex", "Reed"],
    delivery: "Tight, alert, slightly impatient. Sounds like he is listening to another screen while talking.",
  },
  commodities: {
    label: "Dockside Physical",
    rate: 0.9,
    pitch: 0.74,
    preferredVoiceHints: ["Fred", "Daniel", "Alex", "Reed"],
    delivery: "Rough, deliberate, unimpressed by spreadsheets.",
  },
  geo_weather: {
    label: "Storm Room Prophet",
    rate: 0.94,
    pitch: 0.84,
    preferredVoiceHints: ["Daniel", "Alex", "Reed", "Aaron"],
    delivery: "Foreboding without melodrama. Every base case has a storm cloud behind it.",
  },
  skeptic: {
    label: "Red-Team Knife",
    rate: 1.02,
    pitch: 0.8,
    preferredVoiceHints: ["Fred", "Alex", "Daniel", "Reed"],
    delivery: "Sharp, clipped, amused by other people's confidence.",
  },
  portfolio: {
    label: "Risk Desk Adult",
    rate: 0.94,
    pitch: 0.86,
    preferredVoiceHints: ["Alex", "Daniel", "Reed", "Aaron"],
    delivery: "Calm, controlled, impossible to bully with excitement.",
  },
};

export function availableSpeechVoices(): SpeechSynthesisVoice[] {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return [];
  return window.speechSynthesis.getVoices();
}

export function pickSpeechVoice(key: LivingCastKey, voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  const profile = V77_VOICE_PROFILES[key];
  for (const hint of profile.preferredVoiceHints) {
    const found = voices.find((voice) => voice.name.toLowerCase().includes(hint.toLowerCase()));
    if (found) return found;
  }
  return voices.find((voice) => /^en[-_]/i.test(voice.lang)) ?? voices[0] ?? null;
}

export function speakV77Line(
  key: LivingCastKey,
  text: string,
  volume: number,
  voices: SpeechSynthesisVoice[],
  onStart?: () => void,
  onEnd?: () => void,
): SpeechSynthesisUtterance | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
  const profile = V77_VOICE_PROFILES[key];
  const utterance = new SpeechSynthesisUtterance(text);
  const voice = pickSpeechVoice(key, voices);
  if (voice) utterance.voice = voice;
  utterance.rate = profile.rate;
  utterance.pitch = profile.pitch;
  utterance.volume = Math.max(0, Math.min(1, volume));
  if (onStart) utterance.onstart = onStart;
  if (onEnd) utterance.onend = onEnd;
  utterance.onerror = () => onEnd?.();
  window.speechSynthesis.speak(utterance);
  return utterance;
}

export function stopV77Speech() {
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
}

export type V77AmbienceHandle = {
  stop: () => void;
  setVolume: (value: number) => void;
};

export function startV77RoomAmbience(room: V76RoomKey, masterVolume: number): V77AmbienceHandle | null {
  if (typeof window === "undefined") return null;
  const AudioCtor = window.AudioContext ?? (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtor) return null;

  const context = new AudioCtor();
  const master = context.createGain();
  master.gain.value = Math.max(0, Math.min(0.035, masterVolume * 0.035));
  master.connect(context.destination);

  const buffer = context.createBuffer(1, context.sampleRate * 2, context.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i += 1) data[i] = Math.random() * 2 - 1;
  const noise = context.createBufferSource();
  noise.buffer = buffer;
  noise.loop = true;

  const filter = context.createBiquadFilter();
  filter.type = "bandpass";
  const roomFreq: Record<V76RoomKey, number> = {
    pit: 1450,
    war: 620,
    bullpen: 1100,
    commission: 360,
    risk: 280,
    paper: 900,
    monitoring: 1650,
    learning: 420,
    max: 300,
    unknown: 700,
  };
  filter.frequency.value = roomFreq[room];
  filter.Q.value = room === "commission" || room === "max" ? 0.5 : 0.9;

  noise.connect(filter);
  filter.connect(master);
  noise.start();
  void context.resume();

  return {
    stop: () => {
      try { noise.stop(); } catch { /* already stopped */ }
      void context.close();
    },
    setVolume: (value: number) => {
      master.gain.setTargetAtTime(Math.max(0, Math.min(0.035, value * 0.035)), context.currentTime, 0.08);
    },
  };
}

export function playV77SceneCue(room: V76RoomKey, masterVolume: number) {
  if (typeof window === "undefined") return;
  const AudioCtor = window.AudioContext ?? (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtor) return;
  const context = new AudioCtor();
  const osc = context.createOscillator();
  const gain = context.createGain();
  const base: Record<V76RoomKey, number> = {
    pit: 520,
    war: 330,
    bullpen: 440,
    commission: 220,
    risk: 180,
    paper: 610,
    monitoring: 720,
    learning: 260,
    max: 200,
    unknown: 400,
  };
  osc.frequency.value = base[room];
  osc.type = room === "risk" || room === "commission" ? "sine" : "triangle";
  gain.gain.setValueAtTime(0.0001, context.currentTime);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, masterVolume * 0.08), context.currentTime + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.24);
  osc.connect(gain);
  gain.connect(context.destination);
  osc.start();
  osc.stop(context.currentTime + 0.26);
  osc.onended = () => void context.close();
  void context.resume();
}
