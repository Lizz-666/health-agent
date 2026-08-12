// app/lib/core/theme.dart
import 'package:flutter/material.dart';
import 'constants.dart';

class AppTheme {
  static ThemeData get lightTheme => ThemeData(
    brightness: Brightness.light,
    scaffoldBackgroundColor: const Color(AppConstants.bgColor),
    primaryColor: const Color(AppConstants.accentColor),
    colorScheme: const ColorScheme.light(
      primary: Color(AppConstants.accentColor),
      secondary: Color(AppConstants.accentLight),
      surface: Color(AppConstants.bgColor),
      onPrimary: Colors.white,
      onSurface: Color(AppConstants.textColor),
    ),

    // AppBar
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.transparent,
      foregroundColor: Color(AppConstants.textColor),
      elevation: 0,
      scrolledUnderElevation: 0,
    ),

    // Text
    textTheme: const TextTheme(
      bodyLarge: TextStyle(color: Color(AppConstants.textColor), fontSize: 16),
      bodyMedium: TextStyle(color: Color(AppConstants.textColor), fontSize: 15),
      bodySmall: TextStyle(color: Color(AppConstants.textMuted), fontSize: 13),
      titleLarge: TextStyle(
        color: Color(AppConstants.textColor),
        fontSize: 20,
        fontWeight: FontWeight.w600,
      ),
      titleMedium: TextStyle(
        color: Color(AppConstants.textColor),
        fontSize: 18,
        fontWeight: FontWeight.w600,
      ),
    ),

    // ElevatedButton
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: const Color(AppConstants.accentColor),
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
        elevation: 0,
      ),
    ),

    // OutlinedButton
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: const Color(AppConstants.accentColor),
        side: const BorderSide(color: Color(AppConstants.accentColor)),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
      ),
    ),

    // TextButton
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: const Color(AppConstants.textMuted),
      ),
    ),

    // Input
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: const Color(0x30FFFFFF),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: Color(AppConstants.textMuted)),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: Color(AppConstants.textMuted)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(
          color: Color(AppConstants.accentColor),
          width: 2,
        ),
      ),
      labelStyle: const TextStyle(color: Color(AppConstants.textMuted)),
    ),

    // Card
    cardTheme: CardThemeData(
      color: const Color(AppConstants.cardColor),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(color: const Color(AppConstants.glassBorder)),
      ),
      elevation: 0,
    ),

    // Dialog
    dialogTheme: DialogThemeData(
      backgroundColor: const Color(0xD9FFFFFF),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
    ),

    // SnackBar
    snackBarTheme: SnackBarThemeData(
      backgroundColor: const Color(AppConstants.surfaceDark),
      contentTextStyle: const TextStyle(color: Colors.white),
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),

    // Divider
    dividerTheme: const DividerThemeData(
      color: Color(AppConstants.dividerColor),
      thickness: 1,
    ),

    // NavigationBar
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: const Color(
        AppConstants.surfaceDark,
      ).withValues(alpha: 0.95),
      elevation: 0,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      indicatorColor: const Color(
        AppConstants.accentColor,
      ).withValues(alpha: 0.2),
      labelTextStyle: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return const TextStyle(
            color: Color(AppConstants.accentLight),
            fontSize: 12,
            fontWeight: FontWeight.w600,
          );
        }
        return const TextStyle(
          color: Color(AppConstants.navigationMuted),
          fontSize: 12,
        );
      }),
      iconTheme: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return const IconThemeData(color: Color(AppConstants.accentLight));
        }
        return const IconThemeData(color: Color(AppConstants.navigationMuted));
      }),
    ),

    // ProgressIndicator
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: Color(AppConstants.accentColor),
      linearTrackColor: Color(AppConstants.dividerColor),
    ),
  );

  static ThemeData get darkTheme => lightTheme;
}
