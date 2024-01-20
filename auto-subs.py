import stable_whisper
import sys
import time
import re

# some element IDs
winID = "com.blackmagicdesign.resolve.AutoSubsGen"   # should be unique for single instancing
textID = "TextEdit"
addSubsID = "AddSubs"
transcribeID = "Transcribe"
executeAllID = "ExecuteAll"
browseFilesID = "BrowseButton"

ui = fusion.UIManager
dispatcher = bmd.UIDispatcher(ui)

# check for existing instance
win = ui.FindWindow(winID)
if win:
   win.Show()
   win.Raise()
   exit()
# otherwise, we set up a new window

# define the window UI layout
win = dispatcher.AddWindow({
   'ID': winID,
   'Geometry': [ 1450, 100, 450, 600 ],
   'WindowTitle': "Resolve Auto Subtitle Generator",
   },
      ui.VGroup({"ID": "root",},[
      ui.VGap(5),
      ui.Label({ 'Text': "Timeline Text Settings", 'Weight': 0, 'Font': ui.Font({ 'PixelSize': 22 }) }),
      ui.VGap(0),
      ui.Label({ 'Text': "Select track to add subtitles on", 'Weight': 0, 'Font': ui.Font({ 'PixelSize': 13 }) }),
      ui.SpinBox({"ID": "TrackSelector", "Min": 1, "Value": 3}),
      ui.VGap(2),
      ui.Label({ 'Text': "Color of In/Out markers (for selecting area of timeline)", 'Weight': 0, 'Font': ui.Font({ 'PixelSize': 13 }) }),
      ui.ComboBox({"ID": "MarkerColor", 'MaximumSize': [2000, 30]}),
      ui.VGap(15),
      ui.Label({ 'Text': "Advanced Settings:", 'Weight': 1, 'Font': ui.Font({ 'PixelSize': 18 }) }),
      ui.Label({'ID': 'Label', 'Text': 'Use Custom Subtitles File ( .srt )', 'Weight': 0, 'Font': ui.Font({ 'PixelSize': 13 }) }),
      ui.HGroup({'Weight': 0.0, 'MinimumSize': [200, 30]},[
			ui.LineEdit({'ID': 'FileLineTxt', 'Text': '', 'PlaceholderText': 'Please Enter a filepath', 'Weight': 0.9}),
			ui.Button({'ID': 'BrowseButton', 'Text': 'Browse', 'Weight': 0.1}),
		]),
      ui.VGap(2),
      ui.Label({ 'Text': "Format Text", 'Weight': 0, 'Font': ui.Font({ 'PixelSize': 13 }) }),
      ui.ComboBox({"ID": "FormatText", 'MaximumSize': [2000, 30]}),
      ui.CheckBox({"ID": "RemovePunc", "Text": "Remove commas , and full stops .", "Checked": False}),
      ui.VGap(10),
      ui.Label({ 'Text': "# Place markers at the start and end of the area to subtitle.", 'Weight': 1, 'Font': ui.Font({ 'PixelSize': 15 }) }),
      ui.VGap(2),
      ui.HGroup({'Weight': 0.0,},[
         ui.Button({ 'ID': addSubsID, 'Text': "Regenerate Timeline Text", 'MinimumSize': [150, 35], 'MaximumSize': [1000, 35], 'Font': ui.Font({'PixelSize': 13}),}),
      ]),
      ui.VGap(35),
      ui.Label({ 'ID': 'DialogBox', 'Text': "Waiting for Task", 'Weight': 0, 'Font': ui.Font({ 'PixelSize': 20 }), 'Alignment': { 'AlignHCenter': True } }),
      ui.VGap(40)
      ])
   )

itm = win.GetItems()

# Event handlers
def OnClose(ev):
   dispatcher.ExitLoop()

def OnBrowseFiles(ev):
	selectedPath = fusion.RequestFile()
	if selectedPath:
		itm['FileLineTxt'].Text = str(selectedPath)

# Generate Text+ Subtitles on Timeline
def OnGenerate(ev):
   projectManager = resolve.GetProjectManager()
   resolve.OpenPage("edit")
   project = projectManager.GetCurrentProject()
   mediaPool = project.GetMediaPool()
   folder = mediaPool.GetRootFolder()
   items = folder.GetClipList()

   if not project:
      print("No project is loaded")
      return

   # Get current timeline. If no current timeline try to load it from timeline list
   timeline = project.GetCurrentTimeline()
   if not timeline:
      if project.GetTimelineCount() > 0:
         timeline = project.GetTimelineByIndex(1)
         project.SetCurrentTimeline(timeline)
      else:
         print("Current project has no timelines")
         return
   
   if itm['TrackSelector'].Value > timeline.GetTrackCount('video'):
      print("Track not found - Please select a valid track")
      itm['DialogBox'].Text = "Please select a valid track!"
      return
   
   if itm['FileLineTxt'].Text != '': # use custom subtitles file
      file_path = r"{}".format(itm['FileLineTxt'].Text)
      print("Using custom subtitles from -> [", file_path, "]")
   else:
      file_path = storagePath + 'audio.srt' # use generated subtitles file at default location
   
   # READ SRT FILE
   try:
      with open(file_path, mode = 'r', encoding = 'utf-8') as f:
         lines = f.readlines()
   except FileNotFoundError:
      print("No subtitles file (audio.srt) found - Please Transcribe the timeline or load your own SRT file!")
      itm['DialogBox'].Text = "No subtitles file found!"
      return
   
   # Find markers
   markerColor = itm['MarkerColor'].CurrentText
   markers = timeline.GetMarkers()
   marker1 = -1
   marker2 = -1
   for timestamp, marker_info in markers.items():
      color = marker_info['color']
      if marker1 == -1 and color == markerColor:
         marker1 = timestamp
      elif marker2 == -1 and color == markerColor:
         marker2 = timestamp
         break
       
   if marker1 == -1:
      print("Start and end markers not found!")
      itm['DialogBox'].Text = "Please add markers to timeline!"
      return
   elif marker2 == -1:
      print("End marker not found!")
      itm['DialogBox'].Text = "Please add end marker to timeline!"
      return
   
   # Find sound to block censored words (if available)
   subs = []


   if len(lines) < 4:
      print("No subtitles found in SRT file")
      itm['DialogBox'].Text = "No subtitles found in SRT file!"
      return
   
   timelineStartFrame = marker1 + timeline.GetStartFrame()
   timelineEndFrame = marker2 + timeline.GetStartFrame()

   # Create clip object for each line in the SRT file
   for i in range(0, len(lines), 4):
      frame_rate = timeline.GetSetting("timelineFrameRate") # get timeline framerate
      start_time, end_time = lines[i+1].strip().split(" --> ")
      text = lines[i+2].strip() # get  subtitle text
      # Set start position of subtitle (in frames)
      hours, minutes, seconds_milliseconds = start_time.split(':')
      seconds, milliseconds = seconds_milliseconds.split(',')
      posInFrames = int(round((int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000) * round(frame_rate)))
      timelinePos = timelineStartFrame + posInFrames
      #print("->", i//4+1, ":", text, " @ ", timelinePos, " frames")
      # stop subtitles if outside of marker range
      if timelinePos > timelineEndFrame:
         break
      # Set duration of subtitle (in frames)
      hours, minutes, seconds_milliseconds = end_time.split(':')
      seconds, milliseconds = seconds_milliseconds.split(',')
      endPosInFrames = int(round((int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000) * round(frame_rate)))
      duration = (timelineStartFrame + endPosInFrames) - timelinePos
      if itm['FormatText'].CurrentIndex == 1: # make each line lowercase
         text = text.lower()
      elif itm['FormatText'].CurrentIndex == 2: # make each line uppercase
         text = text.upper()
      if itm['RemovePunc'].Checked == True: # remove commas and full stops
         text = text.replace(',', '')
         text = text.replace('.', '')
      # Check for words to censor

      subs.append((timelinePos, duration, text)) # add subtitle to list
   
   print("Found", len(subs), "subtitles in SRT file")
   
   # ADD TEXT+ TO TIMELINE
   templateText = None
   for item in items:
      itemName = item.GetName()
      if itemName == "Text+" or itemName == "Fusion Title" : # Find Text+ in Media Pool
         templateText = item
         print("Found Text+ in Media Pool!")
         break
   if not templateText:
      print("No Text+ found in Media Pool")
      itm['DialogBox'].Text = "No Text+ found in Media Pool!"
      return
   
   print("Adding template subtitles...")
   itm['DialogBox'].Text = "Adding template subtitles..."
   timelineTrack = itm['TrackSelector'].Value # set video track to add subtitles

   for i in range(len(subs)):
      timelinePos, duration, text = subs[i]
      if i < len(subs)-1 and subs[i+1][0] - (timelinePos + duration) < 200: # if gap between subs is less than 10 frames
         duration = (subs[i+1][0] - subs[i][0]) - 1 # set duration to next start frame -1 frame
      newClip = {
         "mediaPoolItem" : templateText,
         "startFrame" : 0,
         "endFrame" : duration,
         "trackIndex" : timelineTrack,
         "recordFrame" : timelinePos
      }
      mediaPool.AppendToTimeline( [newClip] ) # add template Text+ to timeline (text not set yet)
   

   print("Modifying subtitle text content...")
   itm['DialogBox'].Text = "Updating text content..."
   clipList = timeline.GetItemListInTrack('video', timelineTrack) # get list of Text+ in timeline
   i = 0
   for count, clip in enumerate(clipList):
      if clip.GetStart() >= timelineStartFrame and clip.GetStart() < timelineEndFrame:
         text = subs[i][2]
         comp = clip.GetFusionCompByIndex(1) # get fusion comp from Text+
         if (comp is not None):
            toollist = comp.GetToolList().values() # get list of tools in comp
            for tool in toollist:
               if tool.GetAttrs()['TOOLS_Name'] == 'Template' : # find Template tool
                  comp.SetActiveTool(tool)
                  tool.SetInput('StyledText', text)
         if count == len(clipList)-1 or i == len(subs)-1:
            print("Updated text content for", i+1, "subtitles")
            break
         i += 1


   print("Subtitles added to timeline!")
   itm['DialogBox'].Text = "Subtitles added to timeline!"
   projectManager.SaveProject()

# Add the items to the FormatText ComboBox menu
itm['FormatText'].AddItem("None")
itm['FormatText'].AddItem("All Lowercase")
itm['FormatText'].AddItem("All Uppercase")

# Add the items to the MarkerColor ComboBox menu
itm['MarkerColor'].AddItem("Blue")
itm['MarkerColor'].AddItem("Red")
itm['MarkerColor'].AddItem("Green")
itm['MarkerColor'].AddItem("Yellow")
itm['MarkerColor'].AddItem("Pink")


# assign event handlers
win.On[winID].Close     = OnClose
win.On[addSubsID].Clicked  = OnGenerate
win.On[browseFilesID].Clicked = OnBrowseFiles

# Main dispatcher loop
win.Show()
dispatcher.RunLoop()
