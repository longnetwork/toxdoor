# -*- coding: utf-8 -*-

import os, platform

from ctypes import (
    c_void_p, c_char_p, c_wchar_p, POINTER,
    pointer, py_object, cast, string_at, wstring_at,
    c_char, c_wchar,


    _Pointer, _SimpleCData, Array,
)
# from ctypes.util import find_library
from ctypes import cdll


if not (TOXCORE_LIBS := os.environ.get('TOXCORE_LIBS')):
    # TOXCORE_PATH = find_library('toxcore');  # Системный приоритет
    TOXCORE_PATH = None
    
    if not TOXCORE_PATH:                     # Из пакета
        TOXCORE_PATH = os.path.join(os.path.dirname(__file__), '')

        if (platform.system() == "Windows"):
            TOXCORE_PATH = os.path.join(TOXCORE_PATH, 'libtox.dll')
        else:
            TOXCORE_PATH = os.path.join(TOXCORE_PATH, 'libtoxcore.so')
        
else:
    
    if (platform.system() == "Windows"):
        TOXCORE_PATH = os.path.join(TOXCORE_LIBS, 'libtox.dll')
    else:
        TOXCORE_PATH = os.path.join(TOXCORE_LIBS, 'libtoxcore.so')


# При генерации биндингов через ctypeslib2 мы дополнительно через:
# sed -in "s/^_libraries\['FIXME_STUB'\].*/from . import FIXME_STUB; _libraries.update(FIXME_STUB = FIXME_STUB)/" tox_lin.py
# делаем замену в одной строчке, чтобы до того как биндинги проинсталлируются при импорте tox_lin/tox_win нативная либа
# балы уже известна. После импорта ее уже переустановить не получится так как средство ctypeslib2 не предоставляет возможность
# отложенной инициализации, а мы хотим сами искать нативные либы и их юзать


FIXME_STUB = cdll.LoadLibrary(TOXCORE_PATH)

# FIXME tox_win.py и tox_lin отличаются только парой констант ( WORD_SIZE is: 8 / 4 )
if platform.system() == "Windows":
    from . import tox_win as tox
else:
    from . import tox_lin as tox


# sed -in "s/^_libraries\['FIXME_STUB'\].*/from . import FIXME_STUB; _libraries.update(FIXME_STUB = FIXME_STUB)/" tox_lin.py
assert tox._libraries['FIXME_STUB'] is FIXME_STUB



for name in (tox_names := dir(tox)):
    # Просто добавляем в пространство имен tox функции и константы без избыточного префикса tox_/Tox_/TOX_
    
    if name.startswith('tox_') or name.startswith('Tox_') or name.startswith('TOX_'):
        add_name = name[4:]
        assert add_name not in tox_names
        setattr(tox, add_name, getattr(tox, name))


def to_ct(pyobj, ct):
    """
        Типы указателей в ctypes которые созданы не через POINTER(), а также как и скаляры: c_void_p, c_char_p, c_wchar_p

        XXX py_object юзаем как пользовательские данные для которых предусмотрена передача через `void *user_data`
    """
    if ct is None: ct = type(None)
    
    assert not isinstance(pyobj, type) and isinstance(ct, type)


    if ct is c_void_p:
        ct = POINTER(None);  # is c_void_p
    elif ct is c_char_p:
        ct = POINTER(c_char)
    elif ct is c_wchar_p:
        ct = POINTER(c_wchar)

    py = pyobj.encode() if isinstance(pyobj, str) else pyobj
        
    
    if issubclass(ct, _SimpleCData):  # c_void_p проходит в эту ветку
        rt = ct

        if rt is c_void_p:
            # None на входе в params тоже что и c_void_p(None) ( POINTER(None)(None) ) - дают None
            return pointer(py_object(pyobj)) if pyobj is not None else None
        
        if isinstance(py, (bool, int, float)):    # Скаляр
            return rt(py)
            
        return py;  # Вероятно объект уже имеет тип из ctypes. Короткие скаляры в Си передаются обычно по значению
        

    elif issubclass(ct, _Pointer):
        rt = ct._type_;  # ref_type - на какой тип указатель

        if issubclass(rt, _SimpleCData):                        # Указатель на целочисленный тип (это может быть и начало массива)
            if isinstance(py, type(None)):
                return ct(None)
            
            if isinstance(py, (bool, int, float)):              # Указатель на скаляр
                return ct(rt(py))
                
            if isinstance(py, (bytes, tuple)):                  # Указатель на immutable объект
                return (rt * len(py))(*py)
                
            if isinstance(py, (bytearray, memoryview) ):        # Указатель на mutable объект (может меняться по ссылке в самом python-коде)
                return (rt * len(py)).from_buffer(py)
                            
        return pointer(py) if not isinstance(py, _Pointer) else py;  # Вероятно объект уже имеет тип из ctypes и его нужно передавать по ссылке раз мы в ветке _Pointer

    elif issubclass(ct, Array):
        rt = ct._type_;        # тип элемента массива
        length = ct._length_;  # если 0 (для дефиниций вида `type_t data[]`), то нужно трюк с преобразованием типа

        if isinstance(py, (bytes, tuple)):                      # Из immutable массива
            return cast((rt * len(py))(*py), POINTER(rt * length)).contents
            
        if isinstance(py, (bytearray, memoryview) ):            # В mutable массив
            return cast((rt * len(py)).from_buffer(py), POINTER(rt * length)).contents

        if isinstance(py, type(None)):
            return cast((rt * 0)(), POINTER(rt * length)).contents
            
        return pointer(py) if not isinstance(py, _Pointer) else py;  # Массивы обычно в Си передаются не через стек а по ссылке

    else:
        return py


def to_py(ctobj, ct=None):
    """
        Type code   C Type             Minimum size in bytes
        'b'         signed integer     1
        'B'         unsigned integer   1
        'u'         Unicode character  2 (see note)
        'h'         signed integer     2
        'H'         unsigned integer   2
        'i'         signed integer     2
        'I'         unsigned integer   2
        'l'         signed integer     4
        'L'         unsigned integer   4
        'q'         signed integer     8 (see note)
        'Q'         unsigned integer   8 (see note)
        'f'         floating point     4
        'd'         floating point     8

        XXX py_object юзаем как пользовательские данные для которых предусмотрена передача через `void *user_data`

        если в типа данных указатель на c_char / w_char то копируем строки, другие указатели
        возвращаем через memoryview без (без копирования данных)
    """
    
    assert not isinstance(ctobj, type)


    MAX_LENGTH = 2**32;  # Мы не можем в питоне сделать адекватный memoryview на ссылочные данные не зная длину данных
    
    length = MAX_LENGTH
        
    
    if ctobj is None:
        return None

    if isinstance(ctobj, c_void_p):
        ctobj = cast(ctobj, POINTER(None));  # is c_void_p
    elif isinstance(ctobj, c_char_p):
        ctobj = cast(ctobj, POINTER(c_char_p))
    elif isinstance(ctobj, c_wchar_p):
        ctobj = cast(ctobj, POINTER(c_wchar_p))


    if isinstance(ctobj, _SimpleCData):

        if isinstance(ctobj, c_void_p):
            return cast(ctobj, POINTER(py_object)).contents.value;  # если подаем на вход по pointer, то извлекаем - также
            
        return ctobj.value

    elif isinstance(ctobj, _Pointer):
        # Здесь c_void_p не может быть - он перехвачен верхней веткой
        
        rt = ctobj._type_

        if rt is c_char:
            # Строки различимы по последнему завершающему нулю в c-строках (можно применить string_at - она выгребет всю строку)
            return string_at(ctobj).decode(errors='backslashreplace')

        if rt is c_wchar:
            return wstring_at(ctobj).decode(errors='backslashreplace')

        # Это указатель на первый элемент массива (длина или не известна или некая максимально возможная).
        # Нужно что-то вернуть модифицируемое по ссылке указывающее на С-ишную память и это только memoryview в питоне
        typecode = rt._type_

        
        m = memoryview(cast(ctobj, POINTER(rt * length)).contents)
        return m.cast('B').cast(typecode);  # FIXME memoryview может только из байтов преобразовываться в другие типы
            

    elif isinstance(ctobj, Array):
        
        rt = ctobj._type_
        
        _length = ctobj._length_;  # если 0, то так задан в типах указатель на типизированный массив
        if _length:
            length = _length
        
        # Теперь можем работать через memoryview (не копируем данные)
        typecode = rt._type_

        m = memoryview(cast(ctobj, POINTER(rt * length)).contents)
        return m.cast('B').cast(typecode)
        
    else:

        if ct is c_void_p and isinstance(ctobj, int):  # Особый случай интерпретации int как адреса py_object
            return to_py(c_void_p(ctobj))

        return ctobj
        
    



    




