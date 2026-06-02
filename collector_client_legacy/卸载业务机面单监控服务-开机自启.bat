@echo off
setlocal
schtasks /Delete /TN "Order Waybill Monitor Service" /F
echo Deleted startup task: Order Waybill Monitor Service
pause
