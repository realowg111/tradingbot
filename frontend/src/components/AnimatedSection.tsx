/**
 * Animated wrapper components using react-native-reanimated.
 * Provides smooth entrance animations for cards, list items, and counters.
 */
import React, { ReactNode, useEffect } from "react";
import { ViewStyle } from "react-native";
import Animated, {
  FadeInDown,
  FadeIn,
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  withSequence,
  Easing,
} from "react-native-reanimated";

type AnimatedSectionProps = {
  children: ReactNode;
  index?: number;
  delay?: number;
  duration?: number;
  style?: ViewStyle;
};

/** Card / section entrance: fade + small slide up, with stagger via `index`. */
export function AnimatedSection({
  children,
  index = 0,
  delay = 0,
  duration = 380,
  style,
}: AnimatedSectionProps) {
  const totalDelay = delay + index * 60;
  return (
    <Animated.View
      entering={FadeInDown.duration(duration).delay(totalDelay).springify().damping(16)}
      style={style}
    >
      {children}
    </Animated.View>
  );
}

/** Simple fade in for inline content. */
export function FadeBox({
  children,
  delay = 0,
  duration = 320,
  style,
}: {
  children: ReactNode;
  delay?: number;
  duration?: number;
  style?: ViewStyle;
}) {
  return (
    <Animated.View entering={FadeIn.duration(duration).delay(delay)} style={style}>
      {children}
    </Animated.View>
  );
}

/** Pulsing live indicator dot (e.g. for "EN LIGNE"). */
export function PulseDot({
  size = 8,
  color = "#10B981",
  active = true,
}: {
  size?: number;
  color?: string;
  active?: boolean;
}) {
  const scale = useSharedValue(1);
  const opacity = useSharedValue(1);

  useEffect(() => {
    if (active) {
      scale.value = withRepeat(
        withSequence(
          withTiming(1.6, { duration: 800, easing: Easing.inOut(Easing.ease) }),
          withTiming(1, { duration: 800, easing: Easing.inOut(Easing.ease) }),
        ),
        -1,
        false,
      );
      opacity.value = withRepeat(
        withSequence(
          withTiming(0.4, { duration: 800 }),
          withTiming(1, { duration: 800 }),
        ),
        -1,
        false,
      );
    } else {
      scale.value = withTiming(1);
      opacity.value = withTiming(0.5);
    }
  }, [active, opacity, scale]);

  const halo = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    opacity: opacity.value * 0.35,
  }));

  return (
    <Animated.View style={{ width: size * 2, height: size * 2, alignItems: "center", justifyContent: "center" }}>
      <Animated.View
        style={[
          halo,
          {
            position: "absolute",
            width: size,
            height: size,
            borderRadius: size / 2,
            backgroundColor: color,
          },
        ]}
      />
      <Animated.View
        style={{
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: color,
        }}
      />
    </Animated.View>
  );
}
