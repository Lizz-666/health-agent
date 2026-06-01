// app/lib/core/theme.dart
import 'package:flutter/material.dart';
import 'constants.dart';

class AppTheme {
  static ThemeData get darkTheme => ThemeData(
    brightness: Brightness.dark,
    scaffoldBackgroundColor: const Color(AppConstants.bgColor),
    cardColor: const Color(AppConstants.cardColor),
    primaryColor: const Color(AppConstants.primaryColor),
    colorScheme: const ColorScheme.dark(
      primary: Color(AppConstants.primaryColor),
      secondary: Color(AppConstants.accentColor),
      surface: Color(AppConstants.cardColor),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: Color(AppConstants.cardColor),
      foregroundColor: Color(0xFFEAEAEA),
      elevation: 0,
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: const Color(AppConstants.accentColor),
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: const Color(AppConstants.cardColor),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: Color(0xFF0F3460)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: Color(AppConstants.accentColor)),
      ),
    ),
    cardTheme: CardThemeData(
      color: const Color(AppConstants.cardColor),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      elevation: 4,
    ),
  );
}
