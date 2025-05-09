import re
import urllib.request
import json
import os
import glob
import shutil
import zipfile

url = "https://addons.mozilla.org/firefox/downloads/latest/wappalyzer/platform:2/wappalyzer.xpi"
temp = "wappalyzer.zip"
urllib.request.urlretrieve(url, temp)

zippath = "wappalyzer.zip"
exdir = "wappalyzer"
finname = "wappalyzer.xpi"
if not os.path.exists(exdir):
    os.makedirs(exdir)

try:
    # Open the zip file
    with zipfile.ZipFile(zippath, "r") as zip_ref:
        # Extract all the contents into the specified directory
        zip_ref.extractall(exdir)
        print(f"File extracted successfully to {exdir}")
except zipfile.BadZipFile:
    print(f"Error: The file {zippath} is not a valid zip file.")
except FileNotFoundError:
    print(f"Error: The file {zippath} was not found.")
except Exception as e:
    print(f"An error occurred: {e}")

input("Enter to continue")

# File path
file_path = "wappalyzer/js/index.js"  # Update with the file's name
found = 0
# Block of text to replace
old_text = """
 // Save cache
    await setOption(
      'hostnames',
      Object.keys(Driver.cache.hostnames).reduce(
        (hostnames, hostname) => ({
          ...hostnames,
          [hostname]: {
            ...cache,
            detections: Driver.cache.hostnames[hostname].detections
              .filter(({ technology }) => technology)
              .map(
                ({
                  technology: { name: technology },
                  pattern: { regex, confidence },
                  version,
                  rootPath,
                  lastUrl,
                }) => ({
                  technology,
                  pattern: {
                    regex: regex.source,
                    confidence,
                  },
                  version,
                  rootPath,
                  lastUrl,
                })
              ),
          },
        }),
        {}
      )
    )
"""

# New block of text to replace `old_text`
new_text = """
    browser.tabs.create({

        url: JSON.stringify(

        Object.keys(Driver.cache.hostnames).reduce(

          (hostnames, hostname) => ({

            ...hostnames,

            [hostname]: {

              ...cache,

              detections: Driver.cache.hostnames[hostname].detections

                .filter(({ technology }) => technology)

                .map(

                  ({

                    technology: { name: technology },

                    pattern: { regex, confidence },

                    version,

                    rootPath,

                    lastUrl,

                  }) => ({

                    technology,

                    pattern: {

                      regex: regex.source,

                      confidence,

                    },

                    version,

                    rootPath,

                    lastUrl,

                  })

                ),

            },

          }),

          {}

        )

      )

    })
"""

# Block of text to remove
rem = """
    const current = await getOption('version')

    if (!previous) {
      await Driver.clearCache()

      if (current) {
        open(
          'https://www.wappalyzer.com/installed/?utm_source=installed&utm_medium=extension&utm_campaign=wappalyzer'
        )

        const termsAccepted =
          agent === 'chrome' || (await getOption('termsAccepted', false))

        if (!termsAccepted) {
          open(chrome.runtime.getURL('html/terms.html'))
        }
      }
    } else if (current && current !== previous && upgradeMessage) {
      open(
        `https://www.wappalyzer.com/upgraded/?utm_source=upgraded&utm_medium=extension&utm_campaign=wappalyzer`,
        false
      )
    }
"""

# Read, replace, and write back to the file
try:
    with open(file_path, "r") as file:
        content = file.read()

    # Replace `old_text` with `new_text`
    if re.search(re.escape(old_text.strip()), content, flags=re.DOTALL):
        updated_content = re.sub(
            re.escape(old_text.strip()), new_text.strip(), content, flags=re.DOTALL
        )
        print("Replaced the old block of text successfully.")
        found += 1
    else:
        print("Old block of text not found in the file.")
        updated_content = content

    # Remove `rem` block
    if re.search(re.escape(rem.strip()), updated_content, flags=re.DOTALL):
        updated_content = re.sub(
            re.escape(rem.strip()), "", updated_content, flags=re.DOTALL
        )
        print("Removed the specified block of text successfully.")
        found += 1

    else:
        print("Block of text to remove not found in the file.")

    # Write the updated content back to the file
    with open(file_path, "w") as file:
        file.write(updated_content)
    if found == 2:
        print("File updated successfully.")
    else:
        print("hmm looks like there was an error friend!")

    directory = "wappalyzer/technologies"
    output_file = "../wappalyzer/data/technologies.json"
    data = {}
    for filename in glob.glob(os.path.join(directory, "*.json")):
        with open(filename, "r") as file:
            json_data = json.load(file)
            data.update(json_data)
    with open(output_file, "w+") as file:
        json.dump(data, file, indent=4)
    # move wappalyzer/groups.json and wappalyzer/categories.json to current directory
    shutil.copy("wappalyzer/groups.json", "../wappalyzer/data/groups.json")
    shutil.copy("wappalyzer/categories.json", "../wappalyzer/data/categories.json")

except Exception as e:
    print(f"An error occurred: {e}")
try:
    with zipfile.ZipFile(finname, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Walk through the folder
        for foldername, subfolders, filenames in os.walk(exdir):
            for filename in filenames:
                # Create a path to the file
                file_path = os.path.join(foldername, filename)
                # Add the file to the zip with a relative path
                arcname = os.path.relpath(file_path, exdir)
                zipf.write(file_path, arcname)

    print(f"Directory '{exdir}' has been successfully zipped into '{finname}'.")
    shutil.rmtree(exdir)
    os.remove(zippath)
    print(f"successfully deleted extracted directory and '{zippath}' file")
    shutil.move(finname, "../wappalyzer/data/wappalyzer.xpi")
    print(f"moved '{finname} 'to data folder, update succesfull.")
except FileNotFoundError:
    print(f"Error: The directory '{exdir}' was not found.")
except Exception as e:
    print(f"An error occurred: {e}")
