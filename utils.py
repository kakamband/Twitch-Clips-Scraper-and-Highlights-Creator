import youtube_dl, time, os, csv, random, subprocess, shutil
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.common.by import By
from moviepy.editor import VideoFileClip
from datetime import datetime, timedelta
import pandas as pd

def download(url, name):
    """
    Downloads a video from url and saves it in ./temp/ folder
    as name.mkv
    """
    ydl_opts = {'outtmpl': "./temp/" + name + ".mkv"}
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def today_or_yesterday(date):
    """
    Determines if a date given is today or yesterday
    Returns true if it is from today or yesterday
    Returns false otherwise 
    """
    # Date today
    now = datetime.now()
    now_str = now.strftime("%b %d, %Y")
    
    # Date yesterday
    yesterday = datetime.now() - timedelta(days = 1)
    yesterday_str = yesterday.strftime("%b %d, %Y")
    
    if date == now_str or date == yesterday_str:
        return True

    return False

def get_length_video(video):
    """
    Gets the length of video in seconds
    """
    clip = VideoFileClip(video)
    return clip.duration

def build_ffmpeg_input_str(list_of_clip_names):
    """
    Create the string of inputs for use in ffmpeg
    """
    final_str = ""
    for clip in list_of_clip_names:
        final_str += "-i {} ".format("./temp/" + clip)

    return final_str

def scrape_clips():
    """
    Scrapes URLs of top viewed clips in past 24 hours with > 50 viewers
    from specified twitch channels
    Creates clips_data.csv with streamer info, clip URL, and viewer count
    """
    PREV_BROADCASTS = "/videos?filter=archives&sort=time"
    TOP_CLIPS_24_HR = "/clips?filter=clips&range=24hr"

    # Load in all channel URLs from sources.txt and process into a list
    file = open("./sources.txt", "r")
    list_of_channels = list(map(lambda x: x.strip("\n"), file.readlines()))
    file.close()

    # Deletes any existing clips_data.csv
    try:
        os.remove("./clips_data.csv")
    except:
        pass

    # Begin process of scraping clip URLs and writing to clips_data.csv
    with open("./clips_data.csv", "w", newline="") as file:
        writer = csv.writer(file)

        # Write header of clips_data.csv
        writer.writerow(["Channel", "Clip Link", "Views"])

        # Load up Google Chrome browser for scraping
        driver = webdriver.Chrome("./chromedriver.exe")

        # Begin scraping channels
        for channel in list_of_channels:
            driver.get(channel + PREV_BROADCASTS)

            try:
                # Waits until the most recent stream's preview is loaded and scrapes it's title for the date of their last stream
                wait = WebDriverWait(driver, 60)
                prev_stream_element = wait.until(expected_conditions.visibility_of_element_located((By.XPATH, "/html/body/div[1]/div/div[2]/div/main/div[2]/div[3]/div/div/div/div[1]/div[2]/div/div[3]/div/div/div/div/div[2]/div/div[1]/div[1]/article/div[2]/div/div/div[5]/a/div/div/div[1]/div[2]/div/div/div[2]/img")))

                # Continue onto next channel if their last stream was not today or yesterday
                if not today_or_yesterday(prev_stream_element.get_attribute("title")):
                    continue
            except Exception as e:
                # When someone is currently streaming, their previous streams are not shown
                # But since they are streaming, we know that their most recent stream is today
                # So we can just continue on
                pass

            driver.get(channel + TOP_CLIPS_24_HR)

            list_of_clips = list()

            # Waits until the clips section is loaded
            try:
                wait = WebDriverWait(driver, 60)
                preview = wait.until(expected_conditions.visibility_of_element_located((By.XPATH, "/html/body/div[1]/div/div[2]/div/main/div[2]/div[3]/div/div/div/div[1]/div[2]/div/div[3]/div/div/div/div/div[2]/div/div/div[1]/div/div/div/div[1]")))
            except:
                continue

            # Scrapes every single link on the page and adds to list_of_clips if it is a valid clip link
            links = driver.find_elements_by_xpath("//a[@href]")
            for link in links:
                if "clip/" in link.get_attribute("href") and link.get_attribute("href") not in list_of_clips:
                    list_of_clips.append(link.get_attribute("href"))

            # Scrapes the streamer, clip link, and viewer count from each clip
            for clip in list_of_clips:
                driver.get(clip)

                # Waits until view count is loaded and scrapes it
                try:
                    wait = WebDriverWait(driver, 60)
                    view_count = wait.until(expected_conditions.visibility_of_element_located((By.XPATH, "/html/body/div[1]/div/div[2]/div/main/div[2]/div[3]/div/div/div[1]/div[1]/div[2]/div/div[1]/div/div[1]/div[2]/div/div[3]/div/div[1]/div[2]")))
                except:
                    continue

                view_count = int(view_count.text.replace(",", ""))

                if view_count < 50:
                    break

                # Write to clips_data.csv
                writer.writerow([channel, clip, view_count])

def process_clips(length_final_video=1200):
    """
    Reads all of the clips from clips_data.csv, downloads everything,
    and processes everything into one video
    """
    # Read clips_data.csv into pandas and sort by descending views
    clips_df = pd.read_csv("./clips_data.csv")
    clips_df = clips_df.sort_values(by=["Values"], ascending=False)
    clips_links_sorted = list(clips_df["Clip Link"])

    # Initialize counter for file names
    counter = 0
    # Initialize counter for total length of clips combined
    length_clips = 0

    # Deletes existing temp folder and recreates an empty one
    shutil.rmtree("./temp")
    os.mkdir("./temp")

    # Download each clip, name it chronologically, and check for length
    for clip in clips_links_sorted:
        download(clip, str(counter))

        length_clips += get_length_video("./temp/" + str(counter) + ".mkv")
        counter += 1

        if length_clips >= length_final_video:
            break

    # Pause for manual check of all clips
    x = input("Awaiting manual file check")

    # Gets all of the video names from the temp directory and shuffles
    downloaded_clips = os.listdir("./temp")
    random.shuffle(downloaded_clips)

    # Begin merging clips into one video
    merge_clips(downloaded_clips)

def merge_clips(list_of_clip_names):
    # Create command for merging clips
    FFMPEG_STR = "ffmpeg {}-filter_complex \"[0:v] [0:a] [1:v] [1:a] [2:v] [2:a] concat=n={}:v=1:a=1 [v] [a]\" -map \"[v]\" -map \"[a]\" ./temp/combined.mkv".format(build_ffmpeg_input_str(list_of_clips), len(list_of_clips))

    # Passes command through command prompt
    os.system(FFMPEG_STR)

    # Final command for converting final.mkv to final.mp4
    os.system("ffmpeg -i ./temp/combined.mkv -codec copy ./final/final.mp4")

if __name__ == "__main__":
	scrape_clips()
	process_clips()
