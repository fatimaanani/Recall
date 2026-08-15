// resets on hard refresh
let hasPlayed = false;

export function hasSplashPlayed() {
  return hasPlayed;
}

export function markSplashPlayed() {
  hasPlayed = true;
}
