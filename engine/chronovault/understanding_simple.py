"""ChronoVault Understanding System - What Users Actually Ask"""

from __future__ import annotations

import re
from typing import Dict, List


def understand_user_query(query: str) -> Dict:
    """Main function to understand what the user is actually asking"""
    query_lower = query.lower()
    
    # Check for time travel misconceptions
    time_travel_keywords = [
        "time travel", "time machine", "future travel", "past travel",
        "time ka travel", "time machine", "future main jana", "past main jana",
        "time travel karna", "future main chala jana", "past main chala jana"
    ]
    
    time_travel_score = sum(1 for kw in time_travel_keywords if kw in query_lower)
    
    # Check for prediction/statistical questions
    prediction_keywords = [
        "forecast", "prediction", "expect", "predict", "sabse zyada",
        "kitna hoga", "kya hoga", "future", "aage", "baad", "din", "saal",
        "mahine", "hafta", "forecast", "prediction", "trend", "projection",
        "estimate", "expected", "likely", "probably", "chance", "probability",
        "USD/PKR", "bitcoin", "gold", "stock", "currency", "exchange rate"
    ]
    
    prediction_score = sum(1 for kw in prediction_keywords if kw in query_lower)
    
    # Classify intent
    if time_travel_score > 0:
        intent = {
            "primary_intent": "time_travel_misconception",
            "confidence": min(time_travel_score / 3.0, 1.0),
            "explanation": "User appears to think this is actual time travel",
            "clarification_needed": True
        }
        explanation = (
            "Main aapki baat bilkul samajh gaya hain! Ako soch rahe hain ke ChronoVault "
            "actual time travel hai, lekin yeh ek software system hai jo historical data "
            "aur statistical models ka use karke future predictions karta hai.\n\n"
            "Asli time travel abhi physically impossible hai - yeh ek theoretical concept "
            "hai jo physics ke current principles ke against hai. ChronoVault actually:\n"
            "1. Past data analyze karta hai (50+ years ka)\n"
            "2. Statistical models use karta hai (mathematical formulas)\n"
            "3. Current trends dekhta hai (live market data, news)\n"
            "4. Expert opinions combine karta hai (AI agents)\n\n"
            "Yeh actual future se nahi data leta - yeh patterns se estimate karta hai."
        )
    elif prediction_score > 0:
        intent = {
            "primary_intent": "statistical_prediction",
            "confidence": min(prediction_score / 5.0, 1.0),
            "explanation": "User wants statistical predictions about future",
            "clarification_needed": False
        }
        explanation = (
            "Aap statistical predictions ke liye puch rahe hain. ChronoVault yeh karta hai:\n\n"
            "1. **Historical Analysis**: Past 50-100 years ka data analyze karta hai\n"
            "2. **Statistical Modeling**: Mathematical models use karta hai patterns predict karne ke liye\n"
            "3. **Current Trends**: Live market data, news, economic indicators use karta hai\n"
            "4. **Expert Opinions**: AI agents jo experts ki tarah think karte hain\n\n"
            "Important: Ye perfect predictions nahi hote - yeh statistical estimates hain jo "
            "historical patterns par based hote hain. Uncertainty always hoti hai."
        )
    else:
        intent = {
            "primary_intent": "general_question",
            "confidence": 0.5,
            "explanation": "User has a general question",
            "clarification_needed": False
        }
        explanation = (
            "ChronoVault ek sophisticated hai jo historical data, live sources, aur "
            "statistical models combine karta hai future predictions ke liye. Yeh actual "
            "time travel nahi hai - yeh data analysis aur mathematical modeling hai.\n\n"
            "Key features:\n"
            "• 12,380+ keyless endpoints\n"
            "• 70-role AI council\n"
            "• Honest confidence scoring\n"
            "• Scientific basis\n"
            "• No actual time travel"
        )
    
    return {
        "query": query,
        "intent": intent,
        "explanation": explanation,
        "clarification_questions": [],
        "understanding_score": intent["confidence"]
    }