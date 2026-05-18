"""
Test Script untuk Hierarchical Chunking Module
Load cleaned text dari sample file dan test chunking
"""

import json
import requests
from pathlib import Path


def load_sample_text(filepath: str) -> str:
    """Load cleaned text dari file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def test_chunking_via_api(text: str, chunk_size: int = 500, overlap: int = 100):
    """Test hierarchical chunking via API endpoint"""
    
    url = "http://localhost:8000/chunk"
    
    payload = {
        "text": text,
        "doc_type": "UU",
        "chunk_size": chunk_size,
        "overlap": overlap
    }
    
    headers = {"Content-Type": "application/json"}
    
    try:
        print("📤 Sending request to /chunk endpoint...")
        print(f"   URL: {url}")
        print(f"   Text length: {len(text)} chars")
        print(f"   Chunk size: {chunk_size}, Overlap: {overlap}")
        print()
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            
            print("✅ SUCCESS - Hierarchical Chunking Result")
            print("=" * 60)
            
            # Print summary
            summary = result.get('summary', {})
            print("\n📊 SUMMARY:")
            print(f"   Total chunks: {summary.get('total_chunks', 0)}")
            print(f"   By type:")
            by_type = summary.get('by_type', {})
            for type_name, count in by_type.items():
                print(f"      - {type_name}: {count}")
            print(f"   Total chars: {summary.get('total_size_chars', 0)}")
            print(f"   Total words: {summary.get('total_words', 0)}")
            print(f"   Chunks with references: {summary.get('chunks_with_references', 0)}")
            
            # Print chunks detail
            chunks = result.get('chunks', [])
            print(f"\n📦 CHUNKS DETAIL ({len(chunks)} chunks):")
            print("-" * 60)
            
            for i, chunk in enumerate(chunks, 1):
                print(f"\n🔹 Chunk {i}:")
                print(f"   ID: {chunk.get('chunk_id')}")
                print(f"   Type: {chunk.get('section_type')}")
                print(f"   Section: Pasal {chunk['section_number'].get('pasal')}", end="")
                
                if chunk['section_number'].get('ayat'):
                    print(f" Ayat {chunk['section_number'].get('ayat')}", end="")
                if chunk['section_number'].get('huruf'):
                    print(f" Huruf {chunk['section_number'].get('huruf')}", end="")
                print()
                
                print(f"   Size: {chunk.get('size')} chars, {chunk.get('word_count')} words")
                
                if chunk.get('references'):
                    print(f"   References: {len(chunk.get('references'))} found")
                    for ref in chunk.get('references'):
                        print(f"      - {ref.get('full_reference')}")
                
                print(f"   Content preview: {chunk.get('content', '')[:100]}...")
            
            # Optionally save full result to JSON
            output_file = "chunking_result.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"\n\n💾 Full result saved to {output_file}")
            
            return result
        
        else:
            print(f"❌ ERROR - Status code: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    
    except requests.exceptions.ConnectionError:
        print("❌ ERROR - Could not connect to API")
        print("   Make sure FastAPI server is running on http://localhost:8000")
        return None
    except Exception as e:
        print(f"❌ ERROR - {str(e)}")
        return None


def test_chunking_local(text: str, chunk_size: int = 500, overlap: int = 100):
    """Test hierarchical chunking directly (tidak perlu API)"""
    
    from app.services.hierarchical_chunker import create_chunker
    
    print("📤 Running hierarchical chunking locally...")
    print(f"   Text length: {len(text)} chars")
    print(f"   Chunk size: {chunk_size}, Overlap: {overlap}")
    print()
    
    try:
        chunker = create_chunker(target_size=chunk_size, overlap=overlap)
        chunks = chunker.chunk_by_pasal(text)
        summary = chunker.get_chunks_summary()
        
        print("✅ SUCCESS - Hierarchical Chunking Result")
        print("=" * 60)
        
        # Print summary
        print("\n📊 SUMMARY:")
        print(f"   Total chunks: {summary.get('total_chunks', 0)}")
        print(f"   By type:")
        by_type = summary.get('by_type', {})
        for type_name, count in by_type.items():
            print(f"      - {type_name}: {count}")
        print(f"   Total chars: {summary.get('total_size_chars', 0)}")
        print(f"   Total words: {summary.get('total_words', 0)}")
        print(f"   Chunks with references: {summary.get('chunks_with_references', 0)}")
        
        # Print chunks detail
        print(f"\n📦 CHUNKS DETAIL ({len(chunks)} chunks):")
        print("-" * 60)
        
        for i, chunk in enumerate(chunks, 1):
            print(f"\n🔹 Chunk {i}:")
            print(f"   ID: {chunk.chunk_id}")
            print(f"   Type: {chunk.section_type}")
            print(f"   Section: Pasal {chunk.section_number.get('pasal')}", end="")
            
            if chunk.section_number.get('ayat'):
                print(f" Ayat {chunk.section_number.get('ayat')}", end="")
            if chunk.section_number.get('huruf'):
                print(f" Huruf {chunk.section_number.get('huruf')}", end="")
            print()
            
            print(f"   Size: {chunk.size} chars, {chunk.word_count} words")
            
            if chunk.references:
                print(f"   References: {len(chunk.references)} found")
                for ref in chunk.references:
                    print(f"      - {ref.get('full_reference')}")
            
            print(f"   Content preview: {chunk.content[:100]}...")
        
        # Save to JSON
        output_file = "chunking_result_local.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "summary": summary,
                "chunks": [chunk.to_dict() for chunk in chunks]
            }, f, indent=2, ensure_ascii=False)
        print(f"\n\n💾 Full result saved to {output_file}")
        
        return chunks
    
    except Exception as e:
        print(f"❌ ERROR - {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("╔════════════════════════════════════════════════╗")
    print("║  HIERARCHICAL CHUNKING - TEST SCRIPT          ║")
    print("╚════════════════════════════════════════════════╝")
    print()
    
    # Load sample cleaned text
    sample_file = Path(__file__).parent / "sample_cleaned_uu.txt"
    
    if not sample_file.exists():
        print(f"❌ Sample file not found: {sample_file}")
        print("   Please create sample_cleaned_uu.txt first")
        return
    
    text = load_sample_text(str(sample_file))
    print(f"✅ Loaded sample text from {sample_file.name}")
    print(f"   Size: {len(text)} characters")
    print()
    
    # Test parameters
    chunk_size = 500
    overlap = 100
    
    print("TEST OPTIONS:")
    print("1. Via API (/chunk endpoint)")
    print("2. Local (direct module)")
    print()
    
    choice = input("Select test method (1 or 2): ").strip()
    
    if choice == "1":
        result = test_chunking_via_api(text, chunk_size, overlap)
    elif choice == "2":
        result = test_chunking_local(text, chunk_size, overlap)
    else:
        print("❌ Invalid choice")
        return
    
    if result:
        print("\n\n✅ Testing completed successfully!")
    else:
        print("\n\n❌ Testing failed!")


if __name__ == "__main__":
    main()
