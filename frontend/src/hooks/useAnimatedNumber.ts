// Animated value formatting helpers
import { useEffect, useRef, useState } from "react";
import { Animated, Easing } from "react-native";

export function useAnimatedNumber(value: number, durationMs: number = 600) {
  const [display, setDisplay] = useState(value);
  const prev = useRef(value);
  useEffect(() => {
    if (prev.current === value) return;
    const start = prev.current;
    const end = value;
    const startTs = Date.now();
    let raf: any;
    const tick = () => {
      const now = Date.now();
      const t = Math.min(1, (now - startTs) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic
      setDisplay(start + (end - start) * eased);
      if (t < 1) {
        raf = requestAnimationFrame(tick);
      } else {
        prev.current = end;
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, durationMs]);
  return display;
}

export function usePulse(trigger: any) {
  const opacity = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    Animated.sequence([
      Animated.timing(opacity, { toValue: 0.5, duration: 150, useNativeDriver: true, easing: Easing.out(Easing.ease) }),
      Animated.timing(opacity, { toValue: 1, duration: 400, useNativeDriver: true, easing: Easing.out(Easing.ease) }),
    ]).start();
  }, [trigger]);
  return opacity;
}
