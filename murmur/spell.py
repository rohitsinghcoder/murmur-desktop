"""Whether a word is in Windows' own English dictionary (the Windows Spell Checking API,
ISpellChecker, Windows 8+). Used by learn.py to tell vocabulary fixes ("onyx" -> "onnx") from
ordinary word swaps ("Tuesday" -> "Thursday"). No data shipped, nothing leaves the machine.

Note: ISpellChecker.Check also consults the user's own added words (%AppData%\\Microsoft\\Spelling).
"""
import ctypes
from ctypes import HRESULT, POINTER, c_void_p, c_ulong, c_int
from ctypes.wintypes import BOOL, LPCWSTR, LPWSTR

import comtypes
import comtypes.client
from comtypes import GUID, COMMETHOD, IUnknown


class ISpellingError(IUnknown):
    _iid_ = GUID("{B7C82D61-FBE8-4B47-9B27-6C0D2E0DE0A3}")
    _methods_ = [
        COMMETHOD([], HRESULT, "get_StartIndex", (["out"], POINTER(c_ulong), "v")),
        COMMETHOD([], HRESULT, "get_Length", (["out"], POINTER(c_ulong), "v")),
        COMMETHOD([], HRESULT, "get_CorrectiveAction", (["out"], POINTER(c_int), "v")),
        COMMETHOD([], HRESULT, "get_Replacement", (["out"], POINTER(LPWSTR), "v")),
    ]


class IEnumSpellingError(IUnknown):
    _iid_ = GUID("{803E3BD4-2828-4410-8290-418D1D73C762}")
    _methods_ = [
        COMMETHOD([], HRESULT, "Next", (["out"], POINTER(POINTER(ISpellingError)), "v")),
    ]


class ISpellChecker(IUnknown):
    _iid_ = GUID("{B6FD0B71-E2BC-4653-8D05-F197E412770B}")
    _methods_ = [
        COMMETHOD([], HRESULT, "get_LanguageTag", (["out"], POINTER(LPWSTR), "v")),
        COMMETHOD([], HRESULT, "Check", (["in"], LPCWSTR, "text"),
                  (["out"], POINTER(POINTER(IEnumSpellingError)), "v")),
    ]


class ISpellCheckerFactory(IUnknown):
    _iid_ = GUID("{8E018A9D-2415-4677-BF08-794EA61F94BB}")
    _methods_ = [
        COMMETHOD([], HRESULT, "get_SupportedLanguages", (["out"], POINTER(c_void_p), "v")),
        COMMETHOD([], HRESULT, "IsSupported", (["in"], LPCWSTR, "tag"), (["out"], POINTER(BOOL), "v")),
        COMMETHOD([], HRESULT, "CreateSpellChecker", (["in"], LPCWSTR, "tag"),
                  (["out"], POINTER(POINTER(ISpellChecker)), "v")),
    ]


CLSID_SpellCheckerFactory = GUID("{7AB36653-1796-484B-BDFA-E74F1DB7C1DC}")


class Speller:
    """is_word(word) -> bool. Create and use on one thread (COM)."""

    def __init__(self, tags=("en-US", "en-GB", "en-IN")):
        factory = comtypes.client.CreateObject(CLSID_SpellCheckerFactory, interface=ISpellCheckerFactory)
        self.checker = None
        for tag in tags:
            if factory.IsSupported(tag):
                self.checker = factory.CreateSpellChecker(tag)
                self.tag = tag
                break
        if self.checker is None:
            raise OSError("no English spell checker installed")

    def is_word(self, word: str) -> bool:
        errors = self.checker.Check(word)
        # Next returns S_FALSE (comtypes gives a NULL pointer) when there are no more errors.
        try:
            err = errors.Next()
        except comtypes.COMError:
            return True
        return not bool(err)

