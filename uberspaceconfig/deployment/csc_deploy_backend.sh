#!/bin/bash

# Variables
REPO_URL=$GITHUB_DEPLOY_URL
FOLDER2="src/backend"
DEPLOY_DIR="csc_deploy"
TARGET2="backend"

echo "-----------------------------------------------------------------"
echo "--------------------- CSC DEPLOYMENT SCRIPT ---------------------"
echo "-----------------------------------------------------------------"
echo ""
echo "-----------------------------------------------------------------"
echo "------------------------ INITIALIZATION -------------------------"
echo "-----------------------------------------------------------------"

echo $REPO_URL

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
echo "$FOLDER2" >> .git/info/sparse-checkout

# Checkout the repository
echo "GIT: Checking out main branch..."
git checkout main
echo "GIT: Successfully cloned repository!"
echo "-----------------------------------------------------------------"

# Moving folders to target directory
echo "------------------------ UPDATE FILES ---------------------------"
echo "-----------------------------------------------------------------"
echo "I/O: Moving $FOLDER2 to ../$TARGET2..."
rsync -a --force "$FOLDER2/" "../$TARGET2/"
echo "-----------------------------------------------------------------"

# Restarting backend
echo "-------------------------- PROCESSES ----------------------------"
echo "-----------------------------------------------------------------"
echo "SVR: Restarting backend..."
supervisorctl restart fastapi
echo "-----------------------------------------------------------------"

# Clean up
echo "-------------------------- CLEAN UP -----------------------------"
echo "-----------------------------------------------------------------"
echo "DEPLOY: Cleaning up..."
cd ..
rm -r -f $DEPLOY_DIR

echo "-----------------------------------------------------------------"
echo "------------------- CSC - DEPLOYMENT COMPLETE -------------------"
echo "-----------------------------------------------------------------"
echo "------------------------ PROCESS  STATUS ------------------------"
echo "-----------------------------------------------------------------"
supervisorctl status
echo "-----------------------------------------------------------------"
echo "--------------------------- THE END -----------------------------"
echo "-----------------------------------------------------------------"