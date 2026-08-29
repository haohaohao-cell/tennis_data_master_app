import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "@react-navigation/native";
import { Tabs, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { getUnreadCounts } from "@/api/messages";
import { useAuth } from "@/auth/AuthProvider";
import { colors, tabBarHeight } from "@/theme";

function CreateTabButton() {
  const router = useRouter();

  return (
    <Pressable
      accessibilityLabel="打开创建菜单"
      accessibilityRole="button"
      onPress={() => {
        router.push("/create");
      }}
      style={styles.publishTab}
    >
      <View style={styles.publishCircle}>
        <Ionicons color={colors.inverse} name="add" size={30} />
      </View>
      <Text style={styles.publishLabel}>创建</Text>
    </Pressable>
  );
}

export default function TabLayout() {
  const { accessToken, status } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);

  useFocusEffect(
    useCallback(() => {
      if (status !== "authenticated" || !accessToken) {
        setUnreadCount(0);
        return;
      }
      let active = true;
      void getUnreadCounts(accessToken)
        .then((response) => {
          if (active) {
            setUnreadCount(response.messages_tab_badge_count);
          }
        })
        .catch(() => {
          if (active) {
            setUnreadCount(0);
          }
        });
      return () => {
        active = false;
      };
    }, [accessToken, status]),
  );

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: colors.background },
        tabBarActiveTintColor: colors.ink,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: styles.tabLabel,
        tabBarStyle: styles.tabBar,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "首页",
          tabBarIcon: ({ color, focused }) => (
            <Ionicons color={color} name={focused ? "home" : "home-outline"} size={22} />
          ),
        }}
      />
      <Tabs.Screen
        name="training"
        options={{
          title: "训练",
          tabBarIcon: ({ color, focused }) => (
            <Ionicons color={color} name={focused ? "pulse" : "pulse-outline"} size={22} />
          ),
        }}
      />
      <Tabs.Screen
        name="publish"
        options={{
          title: "创建",
          tabBarButton: () => <CreateTabButton />,
        }}
      />
      <Tabs.Screen
        name="messages"
        options={{
          tabBarBadge: unreadCount > 0 ? (unreadCount > 99 ? "99+" : unreadCount) : undefined,
          tabBarBadgeStyle: styles.tabBadge,
          title: "消息",
          tabBarIcon: ({ color, focused }) => (
            <Ionicons color={color} name={focused ? "chatbubble" : "chatbubble-outline"} size={22} />
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "我的",
          tabBarIcon: ({ color, focused }) => (
            <Ionicons color={color} name={focused ? "person" : "person-outline"} size={22} />
          ),
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: colors.surface,
    borderTopColor: colors.line,
    borderTopWidth: StyleSheet.hairlineWidth,
    height: tabBarHeight,
    overflow: "visible",
    paddingBottom: 8,
    paddingTop: 8,
  },
  tabLabel: {
    fontSize: 11,
    fontWeight: "700",
    marginTop: 1,
  },
  tabBadge: {
    backgroundColor: colors.clay,
    color: colors.inverse,
    fontSize: 10,
    fontWeight: "900",
    minWidth: 18,
  },
  publishTab: {
    alignItems: "center",
    justifyContent: "flex-end",
    marginTop: -28,
    width: 64,
  },
  publishCircle: {
    alignItems: "center",
    backgroundColor: colors.accentDeep,
    borderColor: colors.surface,
    borderRadius: 28,
    borderWidth: 3,
    elevation: 5,
    height: 56,
    justifyContent: "center",
    shadowColor: colors.accentDeep,
    shadowOffset: { height: 4, width: 0 },
    shadowOpacity: 0.16,
    shadowRadius: 7,
    width: 56,
  },
  publishLabel: {
    color: colors.inkSoft,
    fontSize: 11,
    fontWeight: "700",
    marginTop: 4,
  },
});
