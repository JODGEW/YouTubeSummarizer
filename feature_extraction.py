from moviepy.editor import VideoFileClip, concatenate_videoclips
import cv2
import numpy as np

def generate_video_summary(video_path):
    cap = cv2.VideoCapture(video_path)
    prev_frame = None
    frame_diffs = []
    frames = []
    ret, frame = cap.read()
    i = 0

    while ret:
        i += 1
        current_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_frame is not None:
            # Calculate the difference between current frame and previous frame
            diff = cv2.absdiff(current_frame, prev_frame)
            diff_sum = np.sum(diff)
            frame_diffs.append(diff_sum)
        prev_frame = current_frame
        ret, frame = cap.read()

    cap.release()

    # Dynamic Threshold adjustment
    mean_diff = np.mean(frame_diffs)
    std_diff = np.std(frame_diffs)
    #! Parameter to change
    multiplier = 0.5
    dynamic_threshold = mean_diff + (std_diff * multiplier)

    # Apply dynamic threshold to select frames
    for i, diff in enumerate(frame_diffs):
        if diff > dynamic_threshold:
            frames.append(i)

    #TODO: Still need to reducing redundancy for the frames
    # Analyze Content Changes Over Time
    window_size = 5
    window_size = min(window_size, len(frame_diffs))
    selected_frames = []
    for i in range(window_size, len(frame_diffs)):
        window_mean = np.mean(frame_diffs[i-window_size:i])
        #if frame_diffs[i] > window_mean * multiplier:
            #frames.append(i)
        if frame_diffs[i] > dynamic_threshold and frame_diffs[i] > window_mean:
            selected_frames.append(i)

    # Check if frames list is empty
    if not frames:
        # Fallback: Select frames at regular intervals if no frames exceeded the threshold
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames > 0:
            interval = max(1, total_frames // 10)
            frames = list(range(0, total_frames, interval))
        else:
            # Handle the error: total_frames is 0 or video couldn't be read
            raise ValueError("Unable to read frames from video.")

    # Ensure frames list has elements before accessing
    if not frames:
        # This check is to handle the case where total_frames might be <= 10 or another issue occurred
        raise ValueError("No key frames identified; unable to proceed with summarization.")

    # Prevent duplicate scenes
    min_gap = 30  # Assuming 30fps, 1 second gap
    if len(frames) > 1:
        key_frames = [frames[0]] + [frames[i] for i in range(1, len(frames)) if frames[i] - frames[i-1] > min_gap]
    else:
        # If we have 0 or 1 frame after the above logic, handle appropriately
        if frames:
            key_frames = frames
        else:
            raise ValueError("No valid key frames available for summarization.")

    # Dynamically adjust clip duration
    video = VideoFileClip(video_path)
    if len(key_frames) > 0:
        average_scene_length = video.duration / len(key_frames)
        clip_duration = max(2, min(5, average_scene_length / 2))  # Ensures min 2s, max 5s per clip
    else:
        clip_duration = 2  # Default if no key frames

    # Extract key frame segments using MoviePy
    clips = []
    for kf in key_frames:
        start_time = max(0, (kf / video.fps) - (clip_duration / 2))
        end_time = min(video.duration, (kf / video.fps) + (clip_duration / 2))
        clips.append(video.subclip(start_time, end_time))

    # Concatenate clips into a summary
    final_clip = concatenate_videoclips(clips)
    summary_path = 'summary_video.mp4'
    final_clip.write_videofile(summary_path)

    return summary_path

# Example
video_path = "./The danger of silence  Clint Smith  TED.mp4"
summary_path = generate_video_summary(video_path)
