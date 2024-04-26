'use client';

import { useState, useEffect, useRef, MutableRefObject } from 'react';
import { Html5Qrcode, Html5QrcodeScanType, Html5QrcodeSupportedFormats } from 'html5-qrcode';
import { Button } from './ui/button';
import { Card, CardContent, CardHeader } from './ui/card';
import { Input } from './ui/input';
import { Badge } from './ui/badge';

const ComponentLookup = () => {
  let config = {
    aspectRatio: 1,
    fps: 10,
    qrbox: {width: 300, height: 300},
    rememberLastUsedCamera: true,
    // Only support camera scan type.
    supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA],
    formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE]
  }

    // { facingMode: "environment" }
    //  && html5QrCode != null

  const [referenceID, setReferenceID] = useState('')
  const [currentID, setCurrentID] = useState('')
  const [inputReferenceID, setInputReferenceID] = useState('')
  const [comparisonResult, setComparisonResult] = useState('')
  const [isScanning, setIsScanning] = useState(false)
  const [borderColor, setBorderColor] = useState('silver')
  const html5QrCodeRef: MutableRefObject<Html5Qrcode | null> = useRef(null)
  const elementId = "reader"
  const cameraContainerId = "cameracontainer"
  const msg_match: string = "IDs Match!"
  const msg_mismatch: string = "Does not Match with Reference ID!"
  const msg_ref_scanned: string = "Reference ID set.\nStart scan for comparison."
  const msg_camera_feed: string = "Camera Feed Placeholder.\n\nTo start comparing IDs,\neither scan or type an ID as reference."

  const startScanningForReference = () => {
      document.getElementById(elementId)?.scrollIntoView()
      if (!html5QrCodeRef.current) {
        html5QrCodeRef.current = new Html5Qrcode(elementId);
      }
      if (html5QrCodeRef.current && !referenceID && !isScanning) {
          setIsScanning(true);
          console.log("Starting scan for reference QR code.");
          Html5Qrcode.getCameras().then(cameras => {
              if (cameras.length && html5QrCodeRef.current != null) {
                html5QrCodeRef.current.start(
                    { facingMode: "environment" },
                      config,
                      decodedText => {
                          setReferenceID(decodedText);
                          setBorderColor('green')
                          setComparisonResult(msg_ref_scanned);
                          stopScanning(); // Stop scanning after setting reference QR Code
                      },
                      undefined
                      // onScanFailure
                  ).catch(err => console.error("Error starting QR scan: ", err));
              } else {
                  console.error("No cameras found.");
              }
          }).catch(err => console.error("Error getting cameras: ", err));
      }
  };

  const startScanningForComparison = () => {
      document.getElementById(elementId)?.scrollIntoView()
      if (!html5QrCodeRef.current) {
        html5QrCodeRef.current = new Html5Qrcode(elementId);
      }
      if (html5QrCodeRef.current && referenceID && !isScanning) {
          setIsScanning(true);
          console.log("Starting scan for comparison QR code.");
          Html5Qrcode.getCameras().then(cameras => {
              if (cameras.length && html5QrCodeRef.current != null) {
                html5QrCodeRef.current.start(
                    { facingMode: "environment" },
                      config,
                      decodedText => {
                          const resultMessage: string = decodedText === referenceID ? msg_match : msg_mismatch
                          if (decodedText === referenceID) {
                            setBorderColor('green')
                            setComparisonResult(resultMessage);
                            setCurrentID(decodedText)
                            stopScanning();
                          } else {
                            setBorderColor('red')
                            setCurrentID(decodedText)
                            setComparisonResult(resultMessage);
                          }
                      },
                      undefined
                      // onScanFailure
                  ).catch(err => console.error("Error starting QR scan: ", err));
              } else {
                  console.error("No cameras found.");
              }
          }).catch(err => console.error("Error getting cameras: ", err));
      }
  };

  const stopScanning = () => {
          html5QrCodeRef.current?.stop().then(() => {
          setIsScanning(false);
          // setBorderColor('silver')
          html5QrCodeRef.current?.clear()
          console.log("Scanning stopped.");
      }).catch(err => {
          console.error("Failed to stop scanning.", err);
      });
};

  const onScanFailure = (error: string) => {
      // console.error(`QR Code scanning error: ${error}`);
      // setIsScanning(false); // Ensure scanning state is reset on failure
  };

  const resetScanner = () => {
    if (isScanning) {
      stopScanning()
    }
    setReferenceID('')
    setComparisonResult('')
    setCurrentID('')
    setInputReferenceID('Reference ID')
    setBorderColor('silver')
  };

  const handleSetInputReferenceID = () => {
    setReferenceID(inputReferenceID);
    setComparisonResult(msg_ref_scanned);
  };

  return (
          <div className="flex flex-col items-center">
            <CardHeader
              className="p-1 relative w-full items-center flex max-w-sm">
            
            {!referenceID && !isScanning &&
              <div className="flex w-full max-w-sm items-center space-x-2 pb-4">
                <Input
                  id="inputFieldReferenceID"
                  placeholder="Reference ID"
                  value={inputReferenceID}
                  onChange={e => setInputReferenceID(e.target.value)}
                />
                <Button
                  variant="outline"
                  className="w-[200px] hover:bg-[#009cda] hover:text-white"
                  onClick={handleSetInputReferenceID}>
                    Set Ref. ID
                </Button>
              </div>
            }

              <div className="w-full grid grid-cols-2 gap-y-4 items-center">
                  
                  {/* Row 1 */}
                  <div className="flex justify-start min-w-0 w-20">
                    <p className="text-lg">Ref. ID: </p>
                  </div>
                  <div className="flex justify-end items-center">
                    <Badge
                      variant="secondary"
                      className={referenceID? "bg-[#009cda] text-white no-wrap flex-shrink-0" : "bg-[#c0c0c0]	no-wrap flex-shrink-0"}>
                        {referenceID || 'Not set'}
                    </Badge>
                  </div>

                  {/* Row 2 */}
                  <div className="flex justify-start min-w-0 w-20">
                    <p className="text-lg">Cur. ID: </p>
                  </div>
                  <div className="flex justify-end items-center">
                    <Badge
                      variant="secondary"
                      className="no-wrap flex-shrink-0"
                      style={{backgroundColor: `${borderColor}`}}>
                        {currentID || 'Not set'}
                    </Badge>
                  </div>
              </div>

            </CardHeader>
            <CardContent
              id={cameraContainerId}
              className="mt-4 p-0 relative w-full max-w-[500px] h-[500px] border-8 rounded-xl"
              style={{borderColor: `${borderColor}`}}>
                <div id={elementId} className="rounded-lg"></div>
              {!isScanning && <div className="absolute inset-0 bg-gray-200 flex items-center text-center justify-center rounded">
              <span className="whitespace-pre-wrap">{comparisonResult? comparisonResult : msg_camera_feed}</span>
              </div>}
            </CardContent>

            <div className="m-4 flex space-y-4 flex-col items-center">

            

            {!referenceID &&
              <Button
                onClick={startScanningForReference}
                variant="outline"
                className="w-[200px] hover:bg-[#009cda] hover:text-white">
                  Start QR Code Scan
              </Button>
            }

            {referenceID && !isScanning &&
              <Button
                onClick={startScanningForComparison}
                variant="outline"
                className="w-[200px] hover:bg-[#009cda] hover:text-white">
                  Start QR Code Scan
              </Button>
            }

            {isScanning &&
              <Button
                onClick={stopScanning}
                variant="outline"
                className="w-[200px] hover:bg-[#009cda] hover:text-white">
                  Stop Scanning
              </Button>
            }

            {!isScanning &&
              <Button
                onClick={resetScanner}
                variant="outline"
                className="m-4 w-[200px] bg-red-500 hover:bg-[#009cda] hover:text-white">
                  Reset
              </Button>
            }
          
          </div>
        </div>
  );
}

export default ComponentLookup
