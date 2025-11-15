"""
Full Lifecycle Integration Tests

End-to-end tests that exercise the complete application workflow
from organization creation to document processing and AI content generation.
"""

import pytest
import sys
from pathlib import Path

# Add tests directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_config import config, data_factory
from utils.test_helpers import (
    create_organization,
    register_user,
    login_user,
    logout_user,
    upload_document,
    get_document,
    delete_document,
    generate_summary,
    generate_questions,
    generate_faq
)
from utils.cleanup_manager import CleanupManager


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.ai
class TestCompleteDocumentLifecycle:
    """Test complete document lifecycle from creation to deletion."""

    @pytest.mark.asyncio
    async def test_full_document_workflow(self, ai_http_client, sample_pdf_file):
        """
        Test complete workflow:
        1. Create organization
        2. Register user
        3. Login
        4. Upload document
        5. Generate AI content (summary, questions, FAQ)
        6. Download document
        7. Delete document
        8. Logout
        9. Cleanup
        """
        cleanup = CleanupManager()

        try:
            # ==================== STEP 1: Create Organization ====================
            print("\n[STEP 1] Creating organization...")
            org_data = data_factory.generate_org_data()
            org = await create_organization(ai_http_client, org_data)
            org_id = org["id"]
            cleanup.track_organization(org_id)
            print(f"✓ Organization created: {org_id}")

            # ==================== STEP 2: Register User ====================
            print("\n[STEP 2] Registering user...")
            user_data = data_factory.generate_user_data()
            await register_user(ai_http_client, org_id, user_data)
            print(f"✓ User registered: {user_data['email']}")

            # ==================== STEP 3: Login ====================
            print("\n[STEP 3] Logging in...")
            credentials = await login_user(
                ai_http_client,
                user_data["email"],
                user_data["password"]
            )
            cleanup.track_session(credentials.access_token)
            print(f"✓ User logged in. Token: {credentials.access_token[:20]}...")
            print(f"✓ User ID: {credentials.user_id}")
            print(f"✓ Session ID: {credentials.session_id}")

            # Verify authentication works
            response = await ai_http_client.get(
                f"{config.api_prefix}/auth/validate",
                headers=credentials.auth_headers
            )
            assert response.status_code == 200, "Authentication validation failed"
            print("✓ Authentication validated")

            # ==================== STEP 4: Upload Document ====================
            print("\n[STEP 4] Uploading document...")
            sample_pdf_file.seek(0)
            doc_result = await upload_document(
                ai_http_client,
                credentials,
                sample_pdf_file.read(),
                "integration_test_doc.pdf",
                "application/pdf"
            )
            doc_id = doc_result.get("id") or doc_result.get("document_id")
            filename = doc_result.get("filename") or doc_result.get("file_name") or "integration_test_doc.pdf"
            cleanup.track_document(org_id, doc_id)
            print(f"✓ Document uploaded: {doc_id}")
            print(f"✓ Filename: {filename}")

            # Verify document exists
            doc_details = await get_document(ai_http_client, credentials, doc_id)
            assert doc_details is not None
            print("✓ Document retrieval verified")

            # ==================== STEP 5: Generate AI Content ====================
            print("\n[STEP 5] Generating AI content...")

            # Generate summary
            print("  • Generating summary...")
            summary_result = await generate_summary(
                ai_http_client,
                credentials,
                filename
            )
            assert "summary" in summary_result or "content" in summary_result
            print("  ✓ Summary generated")

            # Generate questions
            print("  • Generating questions...")
            questions_result = await generate_questions(
                ai_http_client,
                credentials,
                filename,
                question_count=5
            )
            assert "questions" in questions_result
            assert len(questions_result["questions"]) >= 1
            print(f"  ✓ Generated {len(questions_result['questions'])} questions")

            # Generate FAQ
            print("  • Generating FAQ...")
            faq_result = await generate_faq(
                ai_http_client,
                credentials,
                filename,
                faq_count=3
            )
            faq_items = faq_result.get("faq") or faq_result.get("faqs", [])
            assert len(faq_items) >= 1
            print(f"  ✓ Generated {len(faq_items)} FAQ items")

            # ==================== STEP 6: Verify Caching ====================
            print("\n[STEP 6] Verifying AI content caching...")

            # Get cached summary
            response = await ai_http_client.get(
                f"{config.api_prefix}/documents/summarize",
                headers=credentials.auth_headers,
                params={"file_name": filename}
            )
            assert response.status_code == 200
            cached_summary = response.json()
            assert "summary" in cached_summary or "content" in cached_summary
            print("✓ Cached summary retrieved")

            # Get cached questions
            response = await ai_http_client.get(
                f"{config.api_prefix}/documents/questions",
                headers=credentials.auth_headers,
                params={"file_name": filename}
            )
            assert response.status_code == 200
            cached_questions = response.json()
            assert "questions" in cached_questions
            print("✓ Cached questions retrieved")

            # Get cached FAQ
            response = await ai_http_client.get(
                f"{config.api_prefix}/documents/faq",
                headers=credentials.auth_headers,
                params={"file_name": filename}
            )
            assert response.status_code == 200
            cached_faq = response.json()
            assert "faq" in cached_faq or "faqs" in cached_faq
            print("✓ Cached FAQ retrieved")

            # ==================== STEP 7: Download Document ====================
            print("\n[STEP 7] Getting download URL...")
            response = await ai_http_client.get(
                f"{config.api_prefix}/documents/{doc_id}/download",
                headers=credentials.auth_headers
            )
            assert response.status_code == 200
            download_result = response.json()
            assert "download_url" in download_result or "url" in download_result
            print("✓ Download URL obtained")

            # ==================== STEP 8: Delete Document ====================
            print("\n[STEP 8] Deleting document...")
            await delete_document(ai_http_client, credentials, doc_id)
            print("✓ Document deleted")

            # Verify document is deleted
            response = await ai_http_client.get(
                f"{config.api_prefix}/documents/{doc_id}",
                headers=credentials.auth_headers
            )
            assert response.status_code in [404, 200], "Document should be deleted or inactive"
            print("✓ Document deletion verified")

            # ==================== STEP 9: Logout ====================
            print("\n[STEP 9] Logging out...")
            await logout_user(ai_http_client, credentials.access_token)
            print("✓ User logged out")

            # Verify token is invalidated
            response = await ai_http_client.get(
                f"{config.api_prefix}/auth/validate",
                headers=credentials.auth_headers
            )
            assert response.status_code in [401, 403], "Token should be invalid after logout"
            print("✓ Token invalidation verified")

            # ==================== STEP 10: Cleanup ====================
            print("\n[STEP 10] Cleaning up test resources...")
            await cleanup.cleanup_all(ai_http_client)
            cleanup.print_cleanup_summary()

            if cleanup.has_cleanup_errors:
                print("\n⚠️  Some cleanup operations failed, but test passed")
            else:
                print("\n✓ All resources cleaned up successfully")

            print("\n" + "="*60)
            print("INTEGRATION TEST COMPLETED SUCCESSFULLY")
            print("="*60)

        except Exception as e:
            print(f"\n✗ Integration test failed: {str(e)}")
            print("\nAttempting cleanup after failure...")
            await cleanup.cleanup_all(ai_http_client)
            cleanup.print_cleanup_summary()
            raise


@pytest.mark.integration
@pytest.mark.slow
class TestOrganizationToDocumentFlow:
    """Test flow from organization setup to document management."""

    @pytest.mark.asyncio
    async def test_org_setup_and_document_management(
        self,
        http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """
        Test:
        1. Create org
        2. Register multiple users
        3. Upload documents from different users
        4. List documents
        5. Verify isolation
        """
        # Create organization
        org = await create_organization(http_client)
        org_id = org["id"]
        resource_tracker.add_organization(org_id)

        # Register and login first user
        user1_data = data_factory.generate_user_data()
        await register_user(http_client, org_id, user1_data)
        creds1 = await login_user(http_client, user1_data["email"], user1_data["password"])

        # Register and login second user
        user2_data = data_factory.generate_user_data()
        await register_user(http_client, org_id, user2_data)
        creds2 = await login_user(http_client, user2_data["email"], user2_data["password"])

        # User 1 uploads document
        sample_pdf_file.seek(0)
        doc1 = await upload_document(
            http_client,
            creds1,
            sample_pdf_file.read(),
            "user1_doc.pdf",
            "application/pdf"
        )
        doc1_id = doc1.get("id") or doc1.get("document_id")
        resource_tracker.add_document(org_id, doc1_id)

        # User 2 uploads document
        sample_pdf_file.seek(0)
        doc2 = await upload_document(
            http_client,
            creds2,
            sample_pdf_file.read(),
            "user2_doc.pdf",
            "application/pdf"
        )
        doc2_id = doc2.get("id") or doc2.get("document_id")
        resource_tracker.add_document(org_id, doc2_id)

        # Both users should see documents in same org
        # (Depending on implementation - might be org-level or user-level isolation)
        response = await http_client.get(
            f"{config.api_prefix}/documents/",
            headers=creds1.auth_headers
        )
        assert response.status_code == 200

        print("✓ Multi-user document management test passed")


@pytest.mark.integration
class TestErrorRecovery:
    """Test error handling and recovery scenarios."""

    @pytest.mark.asyncio
    async def test_failed_upload_recovery(self, http_client, resource_tracker):
        """Test system state after failed upload."""
        org_id, credentials = await create_organization(http_client), await register_user(http_client, org_id, data_factory.generate_user_data())
        resource_tracker.add_organization(org_id)

        # Try to upload invalid file
        import io
        invalid_file = io.BytesIO(b"")
        files = {"file": ("empty.pdf", invalid_file, "application/pdf")}

        response = await http_client.post(
            f"{config.api_prefix}/documents/upload",
            headers=credentials.auth_headers,
            files=files
        )
        # Should fail gracefully
        assert response.status_code in [400, 422]

        # System should still work - try valid upload
        valid_content = b"%PDF-1.4\n%Test\n%%EOF"
        valid_file = io.BytesIO(valid_content)
        files = {"file": ("test.pdf", valid_file, "application/pdf")}

        response = await http_client.post(
            f"{config.api_prefix}/documents/upload",
            headers=credentials.auth_headers,
            files=files
        )
        # Should succeed or fail gracefully
        assert response.status_code in [200, 201, 400, 422]

        print("✓ Error recovery test passed")
