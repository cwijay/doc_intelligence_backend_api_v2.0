"""
Simple test script for Document Questions API.
"""

import asyncio
import httpx

BASE_URL = "http://localhost:8000"


async def test_questions():
    """Test the questions endpoints."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Login
        print("1. Authenticating...")
        login_response = await client.post(
            "/api/v1/auth/login",
            json={"email": "tjohns@gmail.com", "password": "Pa**Word1$"},
        )

        if login_response.status_code != 200:
            print(f"Login failed: {login_response.text}")
            return

        auth_data = login_response.json()
        token = auth_data["access_token"]
        org_id = auth_data["user"]["org_id"]
        headers = {"Authorization": f"Bearer {token}"}

        print("✅ Authenticated successfully")
        print(f"   Token: {token[:20]}...")
        print(f"   Org ID: {org_id}")

        # 2. List documents to find a parsed one
        print("\n2. Listing documents...")
        docs_response = await client.get("/api/v1/documents", headers=headers)

        if docs_response.status_code == 200:
            docs_data = docs_response.json()
            if docs_data and "documents" in docs_data:
                documents = docs_data["documents"]
                print(f"✅ Found {len(documents)} documents")

                # Find a parsed document
                parsed_doc = None
                for doc in documents:
                    if doc.get("file_content"):
                        parsed_doc = doc
                        break

                if parsed_doc:
                    filename = parsed_doc["filename"]
                    print(f"   Using document: {filename}")

                    # 3. Clear any existing questions first
                    print(f"\n3. Clearing existing questions for {filename}...")
                    clear_response = await client.put(
                        "/api/v1/documents/questions",
                        headers=headers,
                        params={"file_name": filename},
                        json={"questions": []},
                    )

                    if clear_response.status_code == 200:
                        print("✅ Questions cleared")

                    # 4. Generate questions (should create new)
                    print(f"\n4. Generating questions for {filename} (first time)...")
                    gen_response = await client.post(
                        "/api/v1/documents/questions",
                        headers=headers,
                        params={"file_name": filename},
                        json={
                            "question_count": 5,
                            "prompt": "Generate insightful questions about the document",
                        },
                    )

                    if gen_response.status_code == 201:
                        gen_data = gen_response.json()
                        print(
                            f"✅ Generated {len(gen_data.get('ai_questions', []))} questions"
                        )
                        print(f"   Source: {gen_data.get('source', 'unknown')}")
                        if gen_data.get("ai_questions"):
                            print(f"   Sample: {gen_data['ai_questions'][0][:100]}...")
                    else:
                        print(f"❌ Failed to generate: {gen_response.text}")

                    # 5. Try to generate again (should return existing)
                    print(
                        "\n5. Attempting to generate again (should return existing)..."
                    )
                    gen2_response = await client.post(
                        "/api/v1/documents/questions",
                        headers=headers,
                        params={"file_name": filename},
                        json={
                            "question_count": 10,  # Different count
                            "prompt": "Different prompt",
                        },
                    )

                    if gen2_response.status_code == 201:
                        gen2_data = gen2_response.json()
                        print("✅ Returned questions")
                        print(f"   Source: {gen2_data.get('source', 'unknown')}")
                        print(f"   Count: {len(gen2_data.get('ai_questions', []))}")
                    else:
                        print(f"❌ Failed: {gen2_response.text}")

                    # 6. Get questions
                    print("\n6. Getting questions via GET endpoint...")
                    get_response = await client.get(
                        "/api/v1/documents/questions",
                        headers=headers,
                        params={"file_name": filename},
                    )

                    if get_response.status_code == 200:
                        get_data = get_response.json()
                        print("✅ Retrieved questions")
                        print(
                            f"   Has questions: {get_data.get('has_questions', False)}"
                        )
                        print(f"   Count: {get_data.get('questions_count', 0)}")
                    else:
                        print(f"❌ Failed: {get_response.text}")

                    # 7. Update questions
                    print("\n7. Updating questions with PUT endpoint...")
                    update_response = await client.put(
                        "/api/v1/documents/questions",
                        headers=headers,
                        params={"file_name": filename},
                        json={
                            "questions": [
                                "What is the main topic?",
                                "What are the key points?",
                                "What are the conclusions?",
                            ]
                        },
                    )

                    if update_response.status_code == 200:
                        update_data = update_response.json()
                        print("✅ Updated questions")
                        print(
                            f"   Update type: {update_data.get('update_type', 'unknown')}"
                        )
                        print(
                            f"   New count: {len(update_data.get('ai_questions', []))}"
                        )
                    else:
                        print(f"❌ Failed: {update_response.text}")

                    print("\n✅ All tests completed successfully!")
                else:
                    print(
                        "❌ No parsed documents found. Please parse a document first."
                    )
            else:
                print("❌ No documents found in response")
        else:
            print(f"❌ Failed to list documents: {docs_response.text}")


if __name__ == "__main__":
    asyncio.run(test_questions())
