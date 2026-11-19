#!/usr/bin/env python3
"""
Comprehensive QA Test Suite for ChronoVault 2.2.0
Tests 20 different scenarios to identify and fix issues
"""

import sys
import os
sys.path.insert(0, 'engine')

from chronovault import Chrono, ChronoAnswer, Memory, Oracle
from chronovault.probes import harvest_due, schedule_daily, run_cli, task_status
from chronovault.forecast import forecast, time_dilation_factor, relativistic_time_effects
from chronovault.registry import Registry
import json

def test_relativistic_time_calculations():
    """Test relativistic time calculations"""
    print("\n--- Test Relativistic Time Calculations ---")
    
    # Test time dilation at different speeds
    test_cases = [
        (0, 10),      # At rest
        (10, 10),     # 10% light speed
        (50, 10),     # 50% light speed
        (90, 10),     # 90% light speed
        (99, 10),     # 99% light speed
    ]
    
    for velocity_percent, years in test_cases:
        result = relativistic_time_effects(years, velocity_percent)
        print(f"At {velocity_percent}% light speed: {years} Earth years = {result['traveler_years']:.1f} traveler years (factor: {result['dilation_factor']:.2f})")
    
    return True


def test_qa_scenario(scenario_num, question, expected_badge=None, expected_keywords=None):
    """Test a single QA scenario"""
    print(f"\n--- Test {scenario_num}: {question[:50]}... ---")

    try:
        chrono = Chrono()
        result = chrono.ask(question, ai=False)

        # Check result structure
        if not result or not isinstance(result, ChronoAnswer):
            print(f"❌ FAIL: Invalid result structure")
            return False

        required_fields = ['question', 'answer', 'kind', 'sources', 'confidence', 'badge']
        for field in required_fields:
            if not hasattr(result, field):
                print(f"❌ FAIL: Missing field '{field}'")
                return False

        # Check expected badge
        if expected_badge and result.badge != expected_badge:
            print(f"❌ FAIL: Expected badge '{expected_badge}', got '{result.badge}'")
            return False

        # Check expected keywords
        if expected_keywords:
            answer_text = result.answer.lower()
            missing_keywords = [kw for kw in expected_keywords if kw.lower() not in answer_text]
            if missing_keywords:
                print(f"❌ FAIL: Missing keywords: {missing_keywords}")
                return False

        print(f"✅ PASS: Badge={result.badge}, Confidence={result.confidence:.2f}")
        return True

    except Exception as e:
        print(f"❌ FAIL: Exception - {str(e)}")
        return False

def test_forecast_scenario(scenario_num, target, days, expected_model=None):
    """Test a forecast scenario"""
    print(f"\n--- Forecast Test {scenario_num}: {target} {days} days ---")

    try:
        chrono = Chrono()
        # Use the ask interface for forecasts (as implemented in CLI)
        if "/" in target:
            question = f"{target} {days} din baad kitna hoga?"
        else:
            question = f"{target} {days} din baad kitna hoga?"

        result = chrono.ask(question, ai=False)

        if not result or not isinstance(result, ChronoAnswer):
            print(f"❌ FAIL: Invalid forecast result")
            return False

        fc = result.data.get('forecast') or {}
        required_fields = ['model', 'predicted', 'confidence', 'target_date']
        for field in required_fields:
            if field not in fc:
                print(f"❌ FAIL: Missing field '{field}' in forecast data")
                return False

        if expected_model and fc.get('model') != expected_model:
            print(f"❌ FAIL: Expected model '{expected_model}', got '{fc.get('model')}'")
            return False

        print(f"✅ PASS: Model={fc.get('model')}, Prediction={fc.get('predicted')}, Confidence={fc.get('confidence'):.2f}")
        return True

    except Exception as e:
        print(f"❌ FAIL: Exception - {str(e)}")
        return False

def test_memory_operations():
    """Test memory operations"""
    print("\n--- Memory Operations Test ---")

    try:
        memory = Memory()

        # Test record
        test_result = {
            'kind': 'test',
            'answer': 'test answer',
            'confidence': 0.9,
            'badge': 'TEST'
        }

        record_id = memory.record('test question', test_result, 1000)
        if not record_id:
            print("❌ FAIL: Could not record")
            return False

        # Test history
        history = memory.history(limit=5)
        if not isinstance(history, list) or len(history) == 0:
            print("❌ FAIL: Could not get history")
            return False

        print("✅ PASS: Memory operations working")
        return True

    except Exception as e:
        print(f"❌ FAIL: Exception - {str(e)}")
        return False

def test_oracle_operations():
    """Test oracle operations"""
    print("\n--- Oracle Operations Test ---")

    try:
        oracle = Oracle()

        # Test prophecy registration
        prophecy_id = oracle.register(
            question='test prophecy',
            answer='test prediction',
            confidence=0.8,
            badge='TEST',
            due='2026-12-18'
        )
        if not prophecy_id:
            print("❌ FAIL: Could not register prophecy")
            return False

        # Test prophecy stats
        stats = oracle.stats()
        if not isinstance(stats, dict) or 'prophecies' not in stats:
            print("❌ FAIL: Could not get prophecy stats")
            return False

        print("✅ PASS: Oracle operations working")
        return True

    except Exception as e:
        print(f"❌ FAIL: Exception - {str(e)}")
        return False

def test_probes_operations():
    """Test probes operations"""
    print("\n--- Probes Operations Test ---")

    try:
        oracle = Oracle()

        # Test probe run
        results = harvest_due(oracle, limit=3)
        if not isinstance(results, list):
            print("❌ FAIL: Probe run returned invalid result")
            return False

        # Test probe schedule
        schedule_result = schedule_daily()
        if not schedule_result or not schedule_result.get('ok'):
            print("❌ FAIL: Could not schedule probes")
            return False

        print("✅ PASS: Probes operations working")
        return True

    except Exception as e:
        print(f"❌ FAIL: Exception - {str(e)}")
        return False

def test_registry_operations():
    """Test registry operations"""
    print("\n--- Registry Operations Test ---")

    try:
        registry = Registry()

        # Test search
        results = registry.search('bitcoin', limit=5)
        if not isinstance(results, list) or len(results) == 0:
            print("❌ FAIL: Registry search failed")
            return False

        # Test categories
        categories = registry.by_cat
        if not isinstance(categories, dict) or len(categories) == 0:
            print("❌ FAIL: Registry categories failed")
            return False

        print("✅ PASS: Registry operations working")
        return True

    except Exception as e:
        print(f"❌ FAIL: Exception - {str(e)}")
        return False

def test_edge_cases():
    """Test edge cases"""
    print("\n--- Edge Cases Test ---")

    try:
        chrono = Chrono()

        # Test empty question
        result = chrono.ask("", ai=False)
        if result.badge != "NEED-INPUT" or result.confidence != 0:
            print("❌ FAIL: Empty question should return NEED-INPUT")
            return False
        print("✅ PASS: Empty question correctly rejected")

        # Test very long question
        long_question = "a" * 1000
        result = chrono.ask(long_question, ai=False)
        if not result:
            print("❌ FAIL: Long question failed")
            return False
        print("✅ PASS: Long question handled")

        # Test special characters
        special_question = "What is 2+2=? & test < > \" '"
        result = chrono.ask(special_question, ai=False)
        if not result:
            print("❌ FAIL: Special characters failed")
            return False
        print("✅ PASS: Special characters handled")

        return True

    except Exception as e:
        print(f"❌ FAIL: Exception - {str(e)}")
        return False

def run_comprehensive_tests():
    """Run all comprehensive tests"""
    print("🔍 COMPREHENSIVE QA TEST SUITE - ChronoVault 2.2.0")
    print("=" * 60)

    # Test relativistic time calculations
    test_relativistic_time_calculations()

    test_results = []

    # Test 1-5: Basic functionality
    test_results.append(test_qa_scenario(1, "What is 2+2?", "EXACT-MATH", ["4"]))
    test_results.append(test_qa_scenario(2, "1 Jan 2050 konsa din hoga?", "EXACT-MATH", ["2050-01-01", "Saturday"]))
    test_results.append(test_qa_scenario(3, "Lahore ka mausam kaisa hai?", "LIVE-CONSENSUS", ["lahore", "°c"]))
    test_results.append(test_qa_scenario(4, "USD to PKR", "LIVE-CONSENSUS", ["PKR", "USD"]))
    test_results.append(test_qa_scenario(5, "latest AI news", "LIVE-NEWS", ["AI", "news"]))

    # Test 6-10: Knowledge and archive
    test_results.append(test_qa_scenario(6, "time travel kya hai?", "UNDERSTANDING", ["time", "travel"]))
    test_results.append(test_qa_scenario(7, "Japan ki capital kya hai?", "ARCHIVE", ["Tokyo", "capital"]))
    test_results.append(test_qa_scenario(8, "Pakistan me 2026 ki holidays", "ARCHIVE", ["holidays", "2026"]))
    test_results.append(test_qa_scenario(9, "Lahore me abhi kitne baje hain?", "LIVE", ["lahore", "2026"]))
    test_results.append(test_qa_scenario(10, "Bitcoin price", "LIVE-CONSENSUS", ["btc", "usd"]))

    # Test 11-15: Mathematical calculations
    test_results.append(test_qa_scenario(11, "100000 @ 18% 5 saal compound interest", "EXACT-MATH", ["compound", "faida"]))
    test_results.append(test_qa_scenario(12, "50 lakh ka loan 12% 5 saal EMI", "EXACT-MATH", ["EMI", "loan"]))
    test_results.append(test_qa_scenario(13, "5000 @ 10% 3 saal simple interest", "EXACT-MATH", ["simple", "interest"]))
    test_results.append(test_qa_scenario(14, "1 Jan 2025 se kitne din guzre hain?", "EXACT-MATH", ["din", "2025"]))
    test_results.append(test_qa_scenario(15, "2050 tak kitne din baqi hain?", "EXACT-MATH", ["2050", "din"]))

    # Test 16-18: System operations
    test_results.append(test_memory_operations())
    test_results.append(test_oracle_operations())
    test_results.append(test_probes_operations())

    # Test 19: Registry
    test_results.append(test_registry_operations())

    # Test 20: Edge cases
    test_results.append(test_edge_cases())

    # Test 21-22: Forecast scenarios
    test_results.append(test_forecast_scenario(21, "USD/PKR", 30))
    test_results.append(test_forecast_scenario(22, "BTC", 60))

    # Summary
    passed = sum(test_results)
    total = len(test_results)

    print("\n" + "=" * 60)
    print(f"📊 TEST RESULTS: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 ALL TESTS PASSED! ChronoVault is ready for release.")
        return True
    else:
        print(f"❌ {total - passed} tests failed. Please fix the issues before release.")
        return False

if __name__ == "__main__":
    success = run_comprehensive_tests()
    sys.exit(0 if success else 1)