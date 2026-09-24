// The global mute shortcut — owner execution order, 24 September 2026, §8.
//
// `Command + Shift + M`, working while another application is in front, and doing
// exactly one thing: mute ↔ unmute on a Voice session the owner already started.
//
// Two privacy rules are enforced here rather than hoped for.
//
// **It exists only while Voice is active.** Registration happens when a session
// starts and unregistration when it ends, so with Voice off the key is not bound at
// all. Where a platform cannot unbind it, the controller's own toggle is a hard
// no-op — two guards, because one of them will one day be wrong.
//
// **It cannot start Voice.** There is no path from this module to `getUserMedia`; it
// calls a toggle that refuses unless a session is already active.
//
// If the combination is unavailable because macOS or another application owns it,
// that is surfaced honestly and **no substitute key is chosen silently.**

export const MUTE_SHORTCUT = "CommandOrControl+Shift+M";

/** The owner-facing spelling, for labels. */
export const MUTE_SHORTCUT_LABEL = "⌘⇧M";

export interface ShortcutBinding {
  register(accelerator: string, handler: () => void): Promise<void>;
  unregister(accelerator: string): Promise<void>;
  isRegistered(accelerator: string): Promise<boolean>;
}

/**
 * The Tauri binding, loaded lazily so the module imports cleanly in a browser test
 * and in a build without the plugin present.
 */
export async function tauriBinding(): Promise<ShortcutBinding | null> {
  try {
    const plugin = await import("@tauri-apps/plugin-global-shortcut");
    return {
      register: (accelerator, handler) =>
        plugin.register(accelerator, (event) => {
          // Fire on press, not on release: a handler that ran twice per press
          // would mute and immediately unmute.
          if (event.state === "Pressed") handler();
        }),
      unregister: (accelerator) => plugin.unregister(accelerator),
      isRegistered: (accelerator) => plugin.isRegistered(accelerator),
    };
  } catch {
    return null;
  }
}

export interface ShortcutOutcome {
  registered: boolean;
  /** Said plainly when the key could not be bound. No substitute is chosen. */
  detail: string | null;
}

/** Register the ruled combination, or report honestly why not. */
export async function registerMuteShortcut(
  binding: ShortcutBinding | null,
  toggle: () => void,
): Promise<ShortcutOutcome> {
  if (binding === null) {
    return {
      registered: false,
      detail:
        "the global shortcut is unavailable in this build, so muting works from the " +
        "visible control only",
    };
  }
  try {
    if (await binding.isRegistered(MUTE_SHORTCUT)) {
      // Something already owns it. Say so rather than choosing another key.
      return {
        registered: false,
        detail: `${MUTE_SHORTCUT_LABEL} is already registered by macOS or another application, so it is not bound here`,
      };
    }
    await binding.register(MUTE_SHORTCUT, toggle);
    return { registered: true, detail: null };
  } catch (failure) {
    return {
      registered: false,
      detail:
        failure instanceof Error
          ? `${MUTE_SHORTCUT_LABEL} could not be registered: ${failure.message}`
          : `${MUTE_SHORTCUT_LABEL} could not be registered`,
    };
  }
}

export async function unregisterMuteShortcut(binding: ShortcutBinding | null): Promise<void> {
  if (binding === null) return;
  try {
    await binding.unregister(MUTE_SHORTCUT);
  } catch {
    // Already unbound is the state we wanted.
  }
}
