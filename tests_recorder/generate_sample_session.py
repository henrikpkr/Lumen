#!/usr/bin/env python3
"""
Generate a sample psychotherapy session MP3 for testing the recorder.
Uses macOS 'say' command to create realistic session audio.
"""

import subprocess
import os
import tempfile
from pathlib import Path

def generate_sample_session():
    """Generate a sample psychotherapy session audio file."""
    
    # Sample psychotherapy session transcript
    transcript = """
    Hello, welcome back to our session. How have you been feeling this week?
    
    I've been feeling quite anxious, maybe a 7 out of 10 on the anxiety scale. 
    Work has been really stressful lately, and I'm having trouble sleeping - maybe 6 hours a night.
    
    I'm sorry to hear that. Can you tell me more about what's causing the work stress?
    
    Well, there's this big project due next month, and I keep worrying about meeting the deadline. 
    I find myself checking emails constantly, even late at night.
    
    That sounds exhausting. How is this affecting your daily life?
    
    I'm more irritable with my family, and I've been skipping my morning runs. 
    I just feel like I can't shut my brain off. Even when I try to relax, I'm thinking about work.
    
    Have you tried any coping strategies we discussed last time?
    
    I tried the breathing exercises, and they help a bit in the moment. 
    But I haven't been consistent with the thought records you suggested.
    
    That's okay, progress takes time. Let's work on making those techniques a daily habit. 
    What would be one small step you could take this week?
    
    Maybe I could set specific times to check emails, like only at 9 AM and 2 PM.
    And I could try to do the thought record for at least 3 days this week.
    
    Those are excellent goals. Let's also work on a bedtime routine to improve your sleep. 
    Remember, small changes add up. We'll check in on this next session.
    
    Thank you, I'll try my best.
    
    Great work today. Same time next week?
    
    Yes, that works for me. Goodbye.
    """
    
    print("Generating sample psychotherapy session audio...")
    
    # Create temporary file for the transcript
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(transcript)
        temp_txt = f.name
    
    # Output file path
    output_path = Path.home() / "Desktop" / "sample_psychotherapy_session.aiff"
    output_path.parent.mkdir(exist_ok=True)
    
    try:
        # Use macOS 'say' command to generate audio
        # -v: voice (Alex is a clear male voice)
        # -r: rate (180 words per minute)
        # -f: output file format
        print(f"Converting text to speech using macOS 'say' command...")
        
        subprocess.run([
            "say",
            "-v", "Alex",
            "-r", "180",
            "-f", temp_txt,
            "-o", str(output_path)
        ], check=True)
        
        print(f"✓ AIFF file created: {output_path}")
        
        # Convert to MP3 using ffmpeg (if available)
        mp3_path = output_path.with_suffix('.mp3')
        
        try:
            print("Converting to MP3...")
            subprocess.run([
                "ffmpeg", "-i", str(output_path),
                "-codec:a", "libmp3lame",
                "-qscale:a", "2",
                str(mp3_path),
                "-y"
            ], check=True, capture_output=True)
            print(f"✓ MP3 file created: {mp3_path}")
            print(f"\nYou can now upload {mp3_path.name} to the recorder!")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"\nffmpeg not found. Using AIFF file instead: {output_path}")
            print("Install ffmpeg with: brew install ffmpeg")
            print(f"\nYou can upload {output_path.name} - the recorder accepts AIFF too!")
        
    finally:
        # Cleanup temp file
        os.unlink(temp_txt)
    
    print("\n" + "="*50)
    print("Sample session transcript preview:")
    print(transcript.strip()[:300] + "...")
    print("="*50)

if __name__ == "__main__":
    generate_sample_session()
