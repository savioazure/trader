#!/bin/bash
#
# Main pipeline to run inside the docker and predict action to be taken
# today on a given stock
#

set -e
shopt -s nullglob

usage()
{
    cat <<EOF
usage: $0 -s SYMBOL [-h] [-c CONFIG_FILE]

optional arguments:
  -h, --help      show this help message and exit
  -c CONFIG_FILE, --config CONFIG_FILE
                  Relative path to configuration file to be used (YAML)
                  by predictor and trader (same name).
  -s SYMBOL, --symbol SYMBOL
                  The acronym of the symbol to be retrieved from the
                  stock information provider.
  -n, --no-retrieve
                  Run the pipeline without retrieving the latest OHLCV
                  values from the stock data provider. This option is used
                  when data is manually placed in the temporary file.
EOF
}

#
# Main --check arguments
#
RETRIEVE=true
SYMBOL=""
CONFIG_FILE=params.yaml
while [ "$1" != "" ]; do
    case $1 in
        -c | --config )      shift
                             CONFIG_FILE=$1
                             ;;
        -n | --no-retrieve ) RETRIEVE=false
                             ;;
        -s | --symbol )      shift
                             SYMBOL=$1
                             ;;
        -h | --help )        usage
                             exit
                             ;;
        * )                  usage
                             exit 1
    esac
    shift
done

# Check that argument SYMBOL has been passed
if [[ "$SYMBOL" == "" ]]; then
  usage
  exit 1
fi

# ECHO header
DATE=$(date '+%F %T')
LOGHEADER="$DATE ---------"

# Input files
ROOT_DIR="${PWD}"
OHLC_FILE="../staging/${SYMBOL}/ohlcv.csv"
PREDS_FILE="../staging/${SYMBOL}/predictions.csv"
FORECAST_FILE="../staging/${SYMBOL}/forecast.csv"
RL_MODEL="../staging/${SYMBOL}/rl_model"
PORTFOLIO="../staging/${SYMBOL}/portfolio.json"
SCALER="../staging/${SYMBOL}/scaler.pickle"

# Temporary files
TMP_DIR="/tmp/trader"
TMP_OHLC="${TMP_DIR}/${SYMBOL}/tail_ohlc.csv"
LATEST_ACTION="${TMP_DIR}/${SYMBOL}/tmp_action.json"
LATEST_OHLC="${TMP_DIR}/${SYMBOL}/tmp_ohlc.json"

# Check if arguments are saying that I must run the pipeline without
# retrieving the OHLCV values. If so, the file LATEST_OHLC must be
# manually generated with the values.
if [ "$RETRIEVE" = false ]
then
  if [ -f "$LATEST_OHLC" ]; then
    echo "$LOGHEADER Running without updating OHLCV values from provider"
  else
    echo "$LOGHEADER No-retrieve mode, but $LATEST_OHLC file DOES NOT exist"
    exit 1
  fi
else
  echo "$LOGHEADER Running in NORMAL RETRIEVE mode"
fi

# Create tmp directory if does not exist
if [ ! -d "${TMP_DIR}/${SYMBOL}" ]; then
  echo "$LOGHEADER Creating TMP directories"
  mkdir -p "${TMP_DIR}/${SYMBOL}";
fi

# Backup previous temporary ACTION file
if [ -f "${TMP_ACTION}" ]; then
  echo "$LOGHEADER Backing up previous iteration temporary files"
  mv "${TMP_ACTION}" "${TMP_ACTION}".bak
fi

# Get latest info from OHLC, and update file
if [ "$RETRIEVE" = true ]; then
  echo "$LOGHEADER Retrieving latest OHLC data"
  cd retriever
  python retriever.py --config "${CONFIG_FILE}" --symbol "${SYMBOL}" --file "${OHLC_FILE}"
  volume=`awk -F":" '{print $NF}' "${TMP_OHLC}"|tr -d '"'|tr -d '}'`
  if [ "$volume" = "0" ]; then
    echo "$LOGHEADER Volume is ZERO. Aborting pipeline."
    exit 1
  fi
else
  echo "$LOGHEADER Using manual OHLC file."
fi

# Update the predictions file with yesterday's closing (just retrieved) and
# the latest forecast made (tmp_predictions)
echo "$LOGHEADER Update predictions"
cd "${ROOT_DIR}"/updater
python updater.py predictions --config "${CONFIG_FILE}" --file "${PREDS_FILE}"

# Generate a small sample to run predictions on it (smaller = faster)
echo "$LOGHEADER Generating tmp OHLC file"
head -1 "${OHLC_FILE}" > "${TMP_OHLC}"
tail -90 "${OHLC_FILE}" >> "${TMP_OHLC}"

# Predict What will be the next value for stock, from each network trained.
echo "$LOGHEADER Predicting closing values"
cd ../predictor
python predictor.py predict --config "${CONFIG_FILE}" --file "${TMP_OHLC}"

# Produce the ensemble from all predictions from all networks
echo "$LOGHEADER Computing ensemble"
python predictor.py ensemble --config "${CONFIG_FILE}" --file "${PREDS_FILE}"

# Generate Konkorde index for the latest addition to the OHLC file
echo "$LOGHEADER Computing technical indicators"
cd ../indicators
python indicators.py --today --config "${CONFIG_FILE}" -f "${OHLC_FILE}" --scaler-file "${SCALER}"

# Update the forecast file with
# - the closing for yesterday,
# - the forecast for today
# - the values of the indicator (konkorde) for yesterday closing
echo "$LOGHEADER Updating forecast file"
cd ../updater
python updater.py forecast --config "${CONFIG_FILE}" --file "${FORECAST_FILE}"

# Generate a trading recommendation
echo "$LOGHEADER Running trader"
cd ../trader
python trader.py predict --config "${CONFIG_FILE}" -f "${FORECAST_FILE}" --model "${RL_MODEL}" --portfolio "${PORTFOLIO}"
rv=$?
echo "$LOGHEADER trader returned: ${rv}"

# Extract the action to be taken and base price to send it over.
cd ..
BASEPRICE=`cat ${LATEST_OHLC}|cut -d ',' -f 3|cut -d ':' -f2|tr -d '"'`
ACTION=`cat ${LATEST_ACTION}|tr -d "}"|awk -F ':' '{print $2}'|tr -d '"'`
if [ "$ACTION" == "sell" ]; then
    REFERENCE="minimum at ${BASEPRICE}"
elif [ "$ACTION" == "buy" ]; then
    REFERENCE="maximum at ${BASEPRICE}"
else
    REFERENCE=""
fi
echo "${LOGHEADER} The recommendation is ${ACTION} ${REFERENCE}"

# Simulate the portfolio so far, to check how it goes.
echo "Simulation for existing portfolio ${PORTFOLIO}"
cd trader
python trader.py simulate --config "${CONFIG_FILE}" --no-dump -f "${FORECAST_FILE}" --model "${RL_MODEL}" --debug 0
cd ..
