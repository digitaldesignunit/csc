# CSC - Tutorial 01

# --> ONE HOUR PER GROUP, 4 GROUPS!
# TUESDAY!

## Prerequisites

- Install Rhino 8 and/or update your Rhino 8 to the latest version. This should be something like Version 8 SR23.
- 

## Introduction

- I will introduce you to a component database
- This database stores geometry and metadata on architectural components and objects
- It is web based, so can be accessed and interacted with via the internet in multiple ways
- I call it the "Catalogue of Second Chances" because it was created primarily to give leftover materials, objects and harvested components a second chance, as in reusing them
- During this small workshop, I will explain using some slides, and then we will also have short interactive sessions where you will directly apply the things that I explain in short exercises
- So let's get started!

## Accessing the Database

- The first thing we are going to look at is the so-called "web frontend"
- This enables you to browse the database
- It is available using the url https://ddu.uber.space

- If you open the site, you will not find a lot at first
- This is because to view the database, you need to log-in
- I know - another account - but it is necessary for security and data management reasons
- So let's get hands-on with a 10 minute interactive session

## --> Interactive Session (max. 10 Minutes)

- Please create an account using a chosen username, your tu darmstadt e-mail address and a password right now by navigating to regsiter
- I guarantee you that I will not send you any e-mails
- Remember or save your credentials somewhere - you will need them again!

- Once you are registered, please sign-in with your account credentials

## Web Interface Overview (~10 min.)

- Browsing for Components
- Filtering Components
- Component Preview
- Component Details
- Identifying Physical Components
- Reservation system

- Now you should have a good overview of the way the web frontend works
- Are there any questions?

- Good, if there are no questions right now
- We will proceed with the Grasshopper Interface
- Let's start by downloading the interface: Go to GH Interface in the web frontend
- There you can download the files

## Grasshopper Interface Download (max. 5 minutes)

- You will now have 5 minutes to download the files, open the rhino example file and the grasshopper example file

## Grasshopper Interface #1: Getting Started

- So now we will look at a first basic example that shows us how to use the Grasshopper interface.

## Grasshopper Interface #2: Component Reservation System

...

## Web Interface: Identifying Components

- Let's say we have a physical component that we want to identify

## Resources

- https://ddu.uber.space --> The web frontend of our component database

### For Nerds and Deep Divers (Optional!)

#### Backend API Documentation
All Grasshopper Components that interact with the web database use this REST API for this interaction. The API provides several routes and can be used via standard HTTP requests, i.e. from Python.

If you want to explore the routes in the Web documentation linked below, you can login with your usual username and password.

- https://api.ddu.uber.space/docs