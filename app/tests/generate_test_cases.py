"""
Script để test migration filter & sort functionality
Chạy script này để verify các thay đổi hoạt động đúng
"""

import json
from uuid import uuid4

# Test cases for Kafka messages
test_cases = [
    {
        "name": "Test 1: Price Filter",
        "message": {
            "request_id": str(uuid4()),
            "query_text": "laptop",
            "user_id": str(uuid4()),
            "limit": 10,
            "search_type": "PRODUCT",
            "min_price": 10000000,
            "max_price": 20000000
        },
        "expected": "All products with price between 10M-20M"
    },
    {
        "name": "Test 2: Province Filter",
        "message": {
            "request_id": str(uuid4()),
            "query_text": "laptop",
            "user_id": str(uuid4()),
            "limit": 10,
            "search_type": "PRODUCT",
            "province_filters": ["Hà Nội", "Hồ Chí Minh"]
        },
        "expected": "Only products from Hà Nội or Hồ Chí Minh"
    },
    {
        "name": "Test 3: Sort by Price Ascending",
        "message": {
            "request_id": str(uuid4()),
            "query_text": "laptop",
            "user_id": str(uuid4()),
            "limit": 10,
            "search_type": "PRODUCT",
            "sort_by": "price-asc"
        },
        "expected": "Products sorted by price (low to high)"
    },
    {
        "name": "Test 4: Sort by Best-Selling",
        "message": {
            "request_id": str(uuid4()),
            "query_text": "laptop",
            "user_id": str(uuid4()),
            "limit": 10,
            "search_type": "PRODUCT",
            "sort_by": "best-selling"
        },
        "expected": "Products sorted by sale_count (high to low)"
    },
    {
        "name": "Test 5: Combined Filters + Sort",
        "message": {
            "request_id": str(uuid4()),
            "query_text": "laptop",
            "user_id": str(uuid4()),
            "limit": 10,
            "search_type": "PRODUCT",
            "min_price": 10000000,
            "max_price": 20000000,
            "province_filters": ["Hà Nội"],
            "sort_by": "rating"
        },
        "expected": "Price 10M-20M, Hà Nội, sorted by rating"
    },
    {
        "name": "Test 6: Region & Sub-Region Filters",
        "message": {
            "request_id": str(uuid4()),
            "query_text": "laptop",
            "user_id": str(uuid4()),
            "limit": 10,
            "search_type": "PRODUCT",
            "region_filters": ["Miền Bắc"],
            "sub_region_filters": ["Đồng bằng sông Hồng"]
        },
        "expected": "Products from Northern Vietnam, Red River Delta"
    },
    {
        "name": "Test 7: Empty Query (Popular Products)",
        "message": {
            "request_id": str(uuid4()),
            "query_text": "",
            "user_id": str(uuid4()),
            "limit": 10,
            "search_type": "PRODUCT",
            "sort_by": "best-selling"
        },
        "expected": "Popular products sorted by sales"
    },
    {
        "name": "Test 8: Invalid Input Handling",
        "message": {
            "request_id": str(uuid4()),
            "query_text": "laptop",
            "user_id": str(uuid4()),
            "limit": 10,
            "search_type": "PRODUCT",
            "min_price": -1000,
            "max_price": "invalid",
            "sort_by": "invalid-sort"
        },
        "expected": "Should ignore invalid inputs and still return results"
    },
    {
        "name": "Test 9: Backward Compatibility (No Filters)",
        "message": {
            "request_id": str(uuid4()),
            "query_text": "laptop",
            "user_id": str(uuid4()),
            "limit": 10,
            "search_type": "PRODUCT"
        },
        "expected": "Should work like before (no filters/sort)"
    },
    {
        "name": "Test 10: All Filters Combined",
        "message": {
            "request_id": str(uuid4()),
            "query_text": "điện thoại",
            "user_id": str(uuid4()),
            "limit": 20,
            "search_type": "PRODUCT",
            "category_filter_ids": [],  # Add actual category UUIDs if needed
            "min_price": 5000000,
            "max_price": 15000000,
            "province_filters": ["Hà Nội", "Hồ Chí Minh", "Đà Nẵng"],
            "region_filters": ["Miền Bắc"],
            "sort_by": "newest"
        },
        "expected": "Phones, 5M-15M, major cities, Northern Vietnam, newest first"
    }
]


def print_test_case(test):
    """Print test case in formatted way"""
    print("\n" + "="*80)
    print(f"TEST CASE: {test['name']}")
    print("="*80)
    print("\nKafka Message:")
    print(json.dumps(test['message'], indent=2, ensure_ascii=False))
    print(f"\nExpected Result: {test['expected']}")
    print("\n" + "-"*80)


def generate_kafka_commands():
    """Generate commands to send test messages via Kafka console producer"""
    print("\n" + "="*80)
    print("KAFKA CONSOLE PRODUCER COMMANDS")
    print("="*80)
    print("\nTo test, run:")
    print("docker exec -it <kafka-container-name> kafka-console-producer \\")
    print("  --broker-list localhost:9092 \\")
    print("  --topic search_requests")
    print("\nThen paste each test message below:\n")

    for i, test in enumerate(test_cases, 1):
        print(f"\n# Test {i}: {test['name']}")
        print(json.dumps(test['message'], ensure_ascii=False))


def verify_results_template():
    """Generate Python code template to verify results"""
    return """
# Template to verify search results
def verify_price_filter(results, min_price, max_price):
    '''Verify all products are within price range'''
    for product in results:
        price = product.get('price', 0)
        assert min_price <= price <= max_price, f"Price {price} out of range [{min_price}, {max_price}]"
    print(f"✅ Price filter verified: All {len(results)} products within range")


def verify_province_filter(results, province_filters):
    '''Verify all products are from specified provinces'''
    for product in results:
        province = product.get('province_name')
        assert province in province_filters, f"Province {province} not in {province_filters}"
    print(f"✅ Province filter verified: All {len(results)} products from {province_filters}")


def verify_sort_price_asc(results):
    '''Verify products are sorted by price ascending'''
    prices = [p.get('price', 0) for p in results]
    assert prices == sorted(prices), "Products not sorted by price ascending"
    print(f"✅ Sort verified: Products sorted by price (low to high)")


def verify_sort_best_selling(results):
    '''Verify products are sorted by sale_count descending'''
    sales = [p.get('sale_count', 0) for p in results]
    assert sales == sorted(sales, reverse=True), "Products not sorted by sales"
    print(f"✅ Sort verified: Products sorted by sales (high to low)")


def verify_sort_rating(results):
    '''Verify products are sorted by rating descending'''
    ratings = [p.get('rating', 0) for p in results]
    assert ratings == sorted(ratings, reverse=True), "Products not sorted by rating"
    print(f"✅ Sort verified: Products sorted by rating (high to low)")


def verify_sort_newest(results):
    '''Verify products are sorted by createdAt descending'''
    dates = [p.get('createdAt') for p in results if p.get('createdAt')]
    assert dates == sorted(dates, reverse=True), "Products not sorted by date"
    print(f"✅ Sort verified: Products sorted by date (newest first)")


# Example usage:
# results = json.loads(kafka_response)['results']
# verify_price_filter(results, 10000000, 20000000)
# verify_province_filter(results, ["Hà Nội", "Hồ Chí Minh"])
# verify_sort_price_asc(results)
"""


if __name__ == "__main__":
    print("\n" + "="*80)
    print("MIGRATION FILTER & SORT - TEST CASES GENERATOR")
    print("="*80)

    # Print all test cases
    for test in test_cases:
        print_test_case(test)

    # Generate Kafka commands
    generate_kafka_commands()

    # Print verification template
    print("\n" + "="*80)
    print("VERIFICATION CODE TEMPLATE")
    print("="*80)
    print(verify_results_template())

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"\n✅ Generated {len(test_cases)} test cases")
    print("\nNext Steps:")
    print("1. Start your services: docker-compose up -d")
    print("2. Send test messages using Kafka console producer (commands above)")
    print("3. Monitor logs: docker-compose logs -f search-worker")
    print("4. Verify results using verification functions")
    print("\n" + "="*80 + "\n")
