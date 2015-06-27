import os
import re
import random
import gc
from collections import OrderedDict

import search as Search

from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.concatenate import concatenate

usable_extensions = ['mp4', 'avi', 'mov', 'mkv', 'm4v']
BATCH_SIZE = 20


def create_timestamps(inputfiles):
    audiogrep.transcribe(inputfiles)


def convert_timespan(timespan):
    """Convert an srt timespan into a start and end timestamp."""
    start, end = timespan.split('-->')
    start = convert_timestamp(start)
    end = convert_timestamp(end)
    return start, end


def convert_timestamp(timestamp):
    """Convert an srt timestamp into seconds."""
    timestamp = timestamp.strip()
    chunk, millis = timestamp.split(',')
    hours, minutes, seconds = chunk.split(':')
    hours = int(hours)
    minutes = int(minutes)
    seconds = int(seconds)
    seconds = seconds + hours * 60 * 60 + minutes * 60 + float(millis) / 1000
    return seconds


def clean_srt(srt):
    """Remove damaging line breaks and numbers from srt files and return a
    dictionary.
    """
    with open(srt, 'r') as f:
        text = f.read()
    text = re.sub(r'^\d+[\n\r]', '', text, flags=re.MULTILINE)
    lines = text.splitlines()
    output = OrderedDict()
    key = ''

    for line in lines:
        line = line.strip()
        if line.find('-->') > -1:
            key = line
            output[key] = ''
        else:
            if key != '':
                output[key] += line + ' '

    return output


def cleanup_log_files(outputfile):
    """Search for and remove temp log files found in the output directory."""
    d = os.path.dirname(os.path.abspath(outputfile))
    logfiles = [f for f in os.listdir(d) if f.endswith('ogg.log')]
    for f in logfiles:
        os.remove(f)


def demo_supercut(composition, padding):
    """Print out timespans to be cut followed by the line number in the srt."""
    for i, c in enumerate(composition):
        line = c['line']
        start = c['start']
        end = c['end']
        if i > 0 and composition[i - 1]['file'] == c['file'] and start < composition[i - 1]['end']:
            start = start + padding
        print "{1} to {2}:\t{0}".format(line, start, end)


def create_supercut(composition, outputfile, padding):
    """Concatenate video clips together and output finished video file to the
    output directory.
    """
    print ("[+] Creating clips.")
    demo_supercut(composition, padding)

    # add padding when necessary
    for (clip, nextclip) in zip(composition, composition[1:]):
        if ((nextclip['file'] == clip['file']) and (nextclip['start'] < clip['end'])):
            nextclip['start'] += padding

    # put all clips together:
    all_filenames = set([c['file'] for c in composition])
    videofileclips = dict([(f, VideoFileClip(f)) for f in all_filenames])
    cut_clips = [videofileclips[c['file']].subclip(c['start'], c['end']) for c in composition]

    print "[+] Concatenating clips."
    final_clip = concatenate(cut_clips)

    print "[+] Writing ouput file."
    final_clip.to_videofile(outputfile, codec="libx264", temp_audiofile='temp-audio.m4a', remove_temp=True, audio_codec='aac')



def create_supercut_in_batches(composition, outputfile, padding):
    """Create & concatenate video clips in groups of size BATCH_SIZE and output
    finished video file to output directory.
    """
    total_clips = len(composition)
    start_index = 0
    end_index = BATCH_SIZE
    batch_comp = []
    while start_index < total_clips:
        filename = outputfile + '.tmp' + str(start_index) + '.mp4'
        try:
            create_supercut(composition[start_index:end_index], filename, padding)
            batch_comp.append(filename)
            gc.collect()
            start_index += BATCH_SIZE
            end_index += BATCH_SIZE
        except:
            start_index += BATCH_SIZE
            end_index += BATCH_SIZE
            next

    clips = [VideoFileClip(filename) for filename in batch_comp]
    video = concatenate(clips)
    video.to_videofile(outputfile, codec="libx264", temp_audiofile='temp-audio.m4a', remove_temp=True, audio_codec='aac')


    # remove partial video files
    for filename in batch_comp:
        os.remove(filename)

    cleanup_log_files(outputfile)


def search_line(line, search, searchtype):
    """Return True if search term is found in given line, False otherwise."""
    if searchtype == 're':
        return re.search(search, line)  #, re.IGNORECASE)
    elif searchtype == 'pos':
        return Search.search_out(line, search)
    elif searchtype == 'hyper':
        return Search.hypernym_search(line, search)


def get_subtitle_files(inputfile):
    """Return a list of subtitle files."""
    srts = []

    for f in inputfile:
        filename = f.split('.')
        filename[-1] = 'srt'
        srt = '.'.join(filename)
        if os.path.isfile(srt):
            srts.append(srt)

    if len(srts) == 0:
        print "[!] No subtitle files were found."
        return False

    return srts

def compose_from_srts(srts, search, searchtype, padding=0, sync=0):
    """Takes a list of subtitle (srt) filenames, search term and search type
    and, returns a list of timestamps for composing a supercut.
    """
    composition = []
    foundSearchTerm = False

    # Iterate over each subtitles file.
    for srt in srts:

        print srt
        lines = clean_srt(srt)

        videofile = ""
        foundVideoFile = False

        print "[+] Searching for video file corresponding to '" + srt + "'."
        for ext in usable_extensions:
            tempVideoFile = srt.replace('.srt', '.' + ext)
            if os.path.isfile(tempVideoFile):
                videofile = tempVideoFile
                foundVideoFile = True
                print "[+] Found '" + tempVideoFile + "'."

        # If a correspndong video file was found for this subtitles file...
        if foundVideoFile:

            # Check that the subtitles file contains subtitles.
            if lines:

                # Iterate over each line in the current subtitles file.
                for timespan in lines.keys():
                    line = lines[timespan].strip()

                    # If this line contains the search term
                    if search_line(line, search, searchtype):

                        foundSearchTerm = True

                        # Extract the timespan for this subtitle.
                        start, end = convert_timespan(timespan)
                        start = start + sync - padding
                        end = end + sync + padding

                        # Record this occurance of the search term.
                        composition.append({'file': videofile, 'time': timespan, 'start': start, 'end': end, 'line': line})

                # If the search was unsuccessful.
                if foundSearchTerm is False:
                    print "[!] Search term '" + search + "'" + " was not found is subtitle file '" + srt + "'."

            # If no subtitles were found in the current file.
            else:
                print "[!] Subtitle file '" + srt + "' is empty."

        # If no video file was found...
        else:
            print "[!] No video file was found which corresponds to subtitle file '" + srt + "'."
            print "[!] The following video formats are currently supported:"
            extList = ""
            for ext in usable_extensions:
                extList += ext + ", "
            print extList

    return composition


def compose_from_transcript(files, search, searchtype):
    """Takes transcripts created by audiogrep/pocketsphinx, a search and search type
    and returns a list of timestamps for creating a supercut"""
    segments = audiogrep.search(search, files, mode=searchtype, regex=True)
    fixed_segments = []
    for seg in segments:
        seg['file'] = seg['file'].replace('.transcription.txt', '')
        seg['line'] = seg['words']
        fixed_segments.append(seg)

    return fixed_segments


def videogrep(inputfile, outputfile, search, searchtype, maxclips=0, padding=0, test=False, randomize=False, sync=0):
    """Search through and find all instances of the search term in an srt or transcript,
    create a supercut around that instance, and output a new video file
    comprised of those supercuts.
    """
    srts = get_subtitle_files(inputfile)
    transcription = audiogrep.convert_timestamps(inputfile)

    padding = padding / 1000.0
    sync = sync / 1000.0
    composition = []
    foundSearchTerm = False

    if srts and searchtype not in ['word', 'fragment', 'franken']:
        composition = compose_from_srts(srts, search, searchtype, padding=padding, sync=sync)
    elif len(transcription) > 0:
        composition = compose_from_transcript(inputfile, search, searchtype)


    # If the search term was not found in any subtitle file...
    if len(composition) == 0:
        print "[!] Search term '" + search + "'" + " was not found in any file."
        exit(1)

    else:
        print "[+] Search term '" + search + "'" + " was found in " + str(len(composition)) + " places."

        if maxclips > 0:
            composition = composition[:maxclips]

        if randomize is True:
            random.shuffle(composition)

        if test is True:
            demo_supercut(composition, padding)
        else:
            if len(composition) > batch_size:
                print "[+} Starting batch job."
                create_supercut_in_batches(composition, outputfile, padding)
            else:
                create_supercut(composition, outputfile, padding)
