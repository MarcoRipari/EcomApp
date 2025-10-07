
import streamlit as st

def not_in_array(array, list):
    missing = not all(col in array for col in list)
    return missing
