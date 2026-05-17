#!/bin/bash

# Variables
REPO_URL=$GITHUB_DEPLOY_URL
DEPLOY_BRANCH="main"
FOLDER1="src/frontend"
DEPLOY_DIR="csc_deploy"
TARGET1="frontend"

echo "-----------------------------------------------------------------"
echo "---------------- CSC FRONTEND DEPLOYMENT SCRIPT -----------------"
echo "-----------------------------------------------------------------"
echo ""
echo "-----------------------------------------------------------------"
echo "------------------------ INITIALIZATION -------------------------"
echo "-----------------------------------------------------------------"

echo $GITHUB_DEPLOY_URL

# Check if the directory does not exist
if [ ! -d "$DEPLOY_DIR" ]; then
  # Create the directory
  mkdir $DEPLOY_DIR
  echo "INIT: Directory $DEPLOY_DIR created."
else
  echo "INIT: Directory $DEPLOY_DIR already exists."
  echo "INIT: Directory $DEPLOY_DIR will be removed and recreated."
  rm -r -f $DEPLOY_DIR
  mkdir $DEPLOY_DIR
fi
echo "-----------------------------------------------------------------"

# Clone the repository
echo "----------------------- PULL REPOSITORY -------------------------"
echo "-----------------------------------------------------------------"
echo "GIT: Cloning Repository..."
git clone --no-checkout $REPO_URL $DEPLOY_DIR
cd $DEPLOY_DIR

# Initialize sparse-checkout
echo "GIT: Init Sparse Checkout..."
git config core.sparseCheckout true

# Add specific folders to sparse-checkout
echo "$FOLDER1" >> .git/info/sparse-checkout

# Checkout the repository
echo "GIT: Checking out main branch..."
git checkout $DEPLOY_BRANCH
echo "GIT: Successfully cloned repository!"
echo "-----------------------------------------------------------------"

# Moving folders to target directory
echo "------------------------ UPDATE FILES ---------------------------"
echo "-----------------------------------------------------------------"
echo "I/O: Moving $FOLDER1 to ../$TARGET1..."
rsync -a --force "$FOLDER1/" "../$TARGET1/"
echo "-----------------------------------------------------------------"

# Restarting backend and stopping frontend for build
echo "-------------------------- PROCESSES ----------------------------"
echo "-----------------------------------------------------------------"
echo "SVR: Stopping frontend..."
supervisorctl stop frontend
echo "-----------------------------------------------------------------"

# Building frontend
echo "------------------------ BUILD FRONTEND -------------------------"
echo "-----------------------------------------------------------------"
echo "NPM: Building frontend..."
cd ../$TARGET1
rm -r .next
npm i
npm run build -- --webpack

# Restarting frontend after build
echo "------------------------- PROCESSES -----------------------------"
echo "-----------------------------------------------------------------"
echo "SVR: Starting frontend..."
supervisorctl start frontend
echo "-----------------------------------------------------------------"

# Clean up
echo "-------------------------- CLEAN UP -----------------------------"
echo "-----------------------------------------------------------------"
echo "DEPLOY: Cleaning up..."
cd ..
rm -r -f $DEPLOY_DIR

echo "-----------------------------------------------------------------"
echo "-------------- CSC - FRONTEND DEPLOYMENT COMPLETE ---------------"
echo "-----------------------------------------------------------------"
echo "------------------------ PROCESS  STATUS ------------------------"
echo "-----------------------------------------------------------------"
supervisorctl status
echo "-----------------------------------------------------------------"
echo "--------------------------- THE END -----------------------------"
echo "-----------------------------------------------------------------"
