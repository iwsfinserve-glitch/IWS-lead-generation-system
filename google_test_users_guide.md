# Gentle Guide: Adding and Removing Test Users in Google Cloud Console

Hello! This step-by-step guide will walk you through how to add new team members (or remove old ones) so they can safely link their Google Calendars and send emails through our application. 

Since the application is in "Testing Mode" on Google, Google requires us to list the email address of every person authorized to use these Google features.

Take a deep breath—we will go through this together, click by click!

---

## What You Need Before You Start
* A computer with internet access.
* The email address of the person you want to add or remove (e.g., `janedoe@gmail.com`).
* Access to the Google account that manages this project's Google Cloud settings.

---

## Step 1: Open the Google Cloud Console website

1. Click on this link or copy and paste it into your internet browser's address bar at the top:
   👉 **[https://console.cloud.google.com/](https://console.cloud.google.com/)**
2. If it asks you to sign in, please sign in using the **administrator Google Account** for this project.

---

## Step 2: Make sure the correct Project is selected

At the very top of your screen, right next to the colorful Google Cloud logo, look for a small box with a dropdown arrow showing a project name.

1. **Look at the box:** If it shows our project name, you are good to go!
2. **If it shows a different name or is empty:** Click on the box. A pop-up window will appear with a list of projects. Double-click on our project name (e.g. `IWS-lead-generation-system` or similar) to select it.

---

## Step 3: Find the "OAuth consent screen"

Think of the "OAuth consent screen" as the security gatekeeper page.

1. At the very top of the page, there is a large search bar that says **"Search resources, services, and products"**.
2. Click inside that search bar, type the words **"OAuth consent screen"**, and press the **Enter** key on your keyboard.
3. In the search results that appear below the search bar, click on **OAuth consent screen** (it usually has a little blue key or shield icon next to it).

---

## Step 4: Adding a New User's Email

Now that you are on the security gatekeeper page:

1. Scroll down the page slowly until you see a section titled **"Test users"**.
2. Right below the "Test users" title, look for a button that has a plus sign and says **"+ ADD USERS"**. Click it.
3. A small sidebar or window will slide out on the right side of your screen.
4. Click inside the text box under **"Email addresses"** and type in the email address of the person you want to add.
   * *Tip: If you want to add more than one person at the same time, you can type their emails separated by a comma (e.g. `firstperson@gmail.com, secondperson@gmail.com`).*
5. Click the blue **"SAVE"** button at the bottom of that sidebar.
6. **Success!** You will now see their email listed in the table of test users. They can now immediately go to the App and connect their Google Account.

---

## Step 5: Removing an Old User's Email

If someone leaves the team and you want to revoke their access:

1. On the same **OAuth consent screen** page, scroll down to the **"Test users"** table.
2. Find the email address of the person you want to remove.
3. Look to the far right of their email address row. You will see a small **trash bin icon** (or a checkbox next to their name and a **"DELETE"** button at the top of the list).
4. Click the **trash bin icon** (or select the checkbox and click **"DELETE"**).
5. A message will pop up asking if you are sure you want to delete them. Click **"CONFIRM"** or **"OK"**.
6. **Done!** Their email address will disappear from the list, and they will no longer have permission to use the Google integration on our app.

---

### 🎉 You did it! 
You are now fully capable of managing who can access the Google Calendar & Email integrations in the system. Bookmark this page or print it out if you need to refer back to it later!
